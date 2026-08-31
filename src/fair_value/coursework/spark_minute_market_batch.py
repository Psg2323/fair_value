from __future__ import annotations

import argparse
from collections.abc import Sequence

from pyspark.sql import DataFrame, SparkSession  # type: ignore[import-not-found]
from pyspark.sql import functions as F
from pyspark.sql.column import Column  # type: ignore[import-not-found]
from pyspark.sql.types import StringType, StructField, StructType  # type: ignore[import-not-found]
from pyspark.sql.window import Window  # type: ignore[import-not-found]

DEFAULT_BOOTSTRAP_SERVERS = "kafka:19092"
DEFAULT_TOPIC = "fair_value.market_price.minute.raw.v1"
DEFAULT_SILVER_PATH = "/opt/fair_value/data/silver/market_price_minute/spark"
DEFAULT_FEATURE_PATH = "/opt/fair_value/data/gold/features/market_state_daily_spark"
DEFAULT_QUARANTINE_PATH = "/opt/fair_value/data/silver/quarantine/minute_price"

RAW_SCHEMA = StructType(
    [
        StructField("ticker", StringType(), nullable=False),
        StructField("trading_date", StringType(), nullable=False),
        StructField("trading_time", StringType(), nullable=False),
        StructField("price", StringType(), nullable=False),
        StructField("volume", StringType(), nullable=False),
        StructField("source", StringType(), nullable=False),
    ]
)
REQUIRED_COLUMNS = (
    "ticker",
    "trading_date",
    "timestamp",
    "price",
    "volume",
    "source",
)
SILVER_COLUMNS = (
    "ticker",
    "trading_date",
    "timestamp",
    "price",
    "volume",
    "source",
)


def parse_and_normalize(kafka_df: DataFrame) -> DataFrame:
    parsed = kafka_df.select(
        F.col("value").cast("string").alias("_raw_value"),
        F.from_json(F.col("value").cast("string"), RAW_SCHEMA).alias("_event"),
        F.col("partition").alias("_kafka_partition"),
        F.col("offset").alias("_kafka_offset"),
        F.col("timestamp").alias("_kafka_timestamp"),
    )
    return parsed.select(
        "_raw_value",
        F.col("_event").isNotNull().alias("_parse_valid"),
        F.trim(F.col("_event.ticker")).alias("ticker"),
        F.to_date(F.col("_event.trading_date"), "yyyyMMdd").alias("trading_date"),
        F.to_timestamp(
            F.concat(F.col("_event.trading_date"), F.col("_event.trading_time")),
            "yyyyMMddHHmmss",
        ).alias("timestamp"),
        F.col("_event.price").cast("long").alias("price"),
        F.col("_event.volume").cast("long").alias("volume"),
        F.trim(F.col("_event.source")).alias("source"),
        "_kafka_partition",
        "_kafka_offset",
        "_kafka_timestamp",
    )


def valid_event() -> Column:
    condition = F.col("_parse_valid")
    for column_name in REQUIRED_COLUMNS:
        condition = condition & F.col(column_name).isNotNull()
    return F.coalesce(
        (
            condition
            & (F.length(F.col("ticker")) > 0)
            & (F.length(F.col("source")) > 0)
            & (F.col("price") > 0)
            & (F.col("volume") >= 0)
        ),
        F.lit(False),
    )


def deduplicate(valid_df: DataFrame) -> DataFrame:
    latest = Window.partitionBy("ticker", "timestamp").orderBy(
        F.col("_kafka_timestamp").desc_nulls_last(),
        F.col("_kafka_partition").desc(),
        F.col("_kafka_offset").desc(),
    )
    return (
        valid_df.withColumn("_dedup_rank", F.row_number().over(latest))
        .filter(F.col("_dedup_rank") == 1)
        .drop("_dedup_rank")
    )


def build_daily_features(silver: DataFrame) -> DataFrame:
    order = Window.partitionBy("ticker", "trading_date").orderBy("timestamp")
    group = Window.partitionBy("ticker", "trading_date")
    working = (
        silver.withColumn(
            "_log_return",
            F.log(F.col("price").cast("double")) - F.log(F.lag("price").over(order).cast("double")),
        )
        .withColumn("_minute_of_day", F.hour("timestamp") * 60 + F.minute("timestamp"))
        .withColumn("_median_volume", F.percentile_approx("volume", 0.5).over(group))
        .withColumn(
            "_volume_spike",
            F.when(F.col("volume") > F.col("_median_volume") * 3, 1).otherwise(0),
        )
    )
    opening = F.col("_minute_of_day") <= 570
    closing = F.col("_minute_of_day") >= 900
    aggregated = working.groupBy("ticker", "trading_date").agg(
        F.count("*").alias("minute_count"),
        F.min_by("price", "timestamp").alias("open_price"),
        F.max_by("price", "timestamp").alias("close_price"),
        F.max("price").alias("high_price"),
        F.min("price").alias("low_price"),
        F.sum("volume").alias("total_volume"),
        F.sum(F.col("price").cast("double") * F.col("volume")).alias("_turnover"),
        F.sqrt(F.sum(F.pow("_log_return", 2))).alias("realized_volatility"),
        F.max_by(F.when(opening, F.col("price")), F.when(opening, F.col("timestamp"))).alias(
            "_opening_end_price"
        ),
        F.min_by(F.when(closing, F.col("price")), F.when(closing, F.col("timestamp"))).alias(
            "_closing_start_price"
        ),
        F.sum(F.when(F.col("_minute_of_day") < 570, F.col("volume")).otherwise(0)).alias(
            "_opening_volume"
        ),
        F.sum(F.when(closing, F.col("volume")).otherwise(0)).alias("_closing_volume"),
        F.max("_log_return").alias("max_1m_return"),
        F.min("_log_return").alias("min_1m_return"),
        F.sum("_volume_spike").alias("volume_spike_count"),
        F.first("source").alias("source"),
    )
    return (
        aggregated.withColumn(
            "vwap",
            F.when(
                F.col("total_volume") > 0,
                F.col("_turnover") / F.col("total_volume"),
            ),
        )
        .withColumn(
            "close_vwap_ratio",
            F.col("close_price").cast("double") / F.col("vwap") - 1,
        )
        .withColumn(
            "opening_return_30m",
            F.col("_opening_end_price").cast("double") / F.col("open_price").cast("double") - 1,
        )
        .withColumn(
            "closing_return_30m",
            F.col("close_price").cast("double") / F.col("_closing_start_price").cast("double") - 1,
        )
        .withColumn(
            "opening_volume_ratio",
            F.col("_opening_volume") / F.col("total_volume"),
        )
        .withColumn(
            "closing_volume_ratio",
            F.col("_closing_volume") / F.col("total_volume"),
        )
        .withColumn(
            "intraday_momentum",
            F.col("close_price").cast("double") / F.col("open_price").cast("double") - 1,
        )
        .withColumn(
            "intraday_reversal",
            F.col("close_price").cast("double") / F.col("high_price").cast("double") - 1,
        )
        .drop(
            "_turnover",
            "_opening_end_price",
            "_closing_start_price",
            "_opening_volume",
            "_closing_volume",
        )
    )


def run_batch(
    spark: SparkSession,
    bootstrap_servers: str,
    topic: str,
    silver_path: str,
    feature_path: str,
    quarantine_path: str,
    fail_before_write: bool,
) -> None:
    kafka_df = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap_servers)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("endingOffsets", "latest")
        .load()
        .cache()
    )
    input_count = kafka_df.count()
    typed = parse_and_normalize(kafka_df).cache()
    parsed_count = typed.filter("_parse_valid").count()
    valid = typed.filter(valid_event()).cache()
    valid_count = valid.count()
    quarantine = typed.filter(~valid_event()).cache()
    quarantine_count = quarantine.count()
    deduplicated = deduplicate(valid).cache()
    deduplicated_count = deduplicated.count()
    silver = deduplicated.select(*SILVER_COLUMNS).cache()
    features = build_daily_features(silver).cache()
    feature_count = features.count()

    print(f"topic={topic}")
    print(f"input_row_count={input_count}")
    print(f"parsed_row_count={parsed_count}")
    print(f"invalid_row_count={input_count - valid_count}")
    print(f"quarantine_row_count={quarantine_count}")
    print(f"duplicate_removed_count={valid_count - deduplicated_count}")
    print(f"silver_row_count={deduplicated_count}")
    print(f"feature_row_count={feature_count}")
    print(f"silver_schema={silver.schema.simpleString()}")

    if fail_before_write:
        raise RuntimeError("Intentional failure before output write")

    silver.write.mode("overwrite").parquet(silver_path)
    features.write.mode("overwrite").parquet(feature_path)
    quarantine.write.mode("overwrite").json(quarantine_path)
    print(f"silver_path={silver_path}")
    print(f"feature_path={feature_path}")
    print(f"quarantine_path={quarantine_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spark batch for KIS minute Kafka events")
    parser.add_argument("--bootstrap-servers", default=DEFAULT_BOOTSTRAP_SERVERS)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--silver-path", default=DEFAULT_SILVER_PATH)
    parser.add_argument("--feature-path", default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--quarantine-path", default=DEFAULT_QUARANTINE_PATH)
    parser.add_argument("--fail-before-write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    spark = SparkSession.builder.appName("fair-value-minute-market-state").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        run_batch(
            spark,
            args.bootstrap_servers,
            args.topic,
            args.silver_path,
            args.feature_path,
            args.quarantine_path,
            args.fail_before_write,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
