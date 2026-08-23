from __future__ import annotations

import argparse
from collections.abc import Sequence

from pyspark.sql import DataFrame, SparkSession  # type: ignore[import-not-found]
from pyspark.sql import functions as F
from pyspark.sql.column import Column  # type: ignore[import-not-found]
from pyspark.sql.types import (  # type: ignore[import-not-found]
    BooleanType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window  # type: ignore[import-not-found]

DEFAULT_BOOTSTRAP_SERVERS = "kafka:19092"
DEFAULT_TOPIC = "fair_value.market_price.raw.v1"
DEFAULT_OUTPUT_PATH = "/opt/fair_value/data/silver/market_price/course_exercise"

RAW_EVENT_SCHEMA = StructType(
    [
        StructField("ticker", StringType(), nullable=False),
        StructField("trading_date", StringType(), nullable=False),
        StructField("open", StringType(), nullable=False),
        StructField("high", StringType(), nullable=False),
        StructField("low", StringType(), nullable=False),
        StructField("close", StringType(), nullable=False),
        StructField("volume", StringType(), nullable=False),
        StructField("source", StringType(), nullable=False),
        StructField("adjusted", BooleanType(), nullable=False),
    ]
)

REQUIRED_COLUMNS = (
    "ticker",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "adjusted",
)

FINAL_COLUMNS = (
    "ticker",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "daily_return",
    "source",
    "adjusted",
)


def parse_kafka_events(kafka_df: DataFrame) -> DataFrame:
    """Decode Kafka values and retain metadata only for deterministic deduplication."""
    with_event = kafka_df.select(
        F.from_json(F.col("value").cast("string"), RAW_EVENT_SCHEMA).alias("_event"),
        F.col("partition").alias("_kafka_partition"),
        F.col("offset").alias("_kafka_offset"),
        F.col("timestamp").alias("_kafka_timestamp"),
    )

    return with_event.select(
        F.col("_event").isNotNull().alias("_parse_valid"),
        F.col("_event.*"),
        "_kafka_partition",
        "_kafka_offset",
        "_kafka_timestamp",
    )


def normalize_types(parsed_df: DataFrame) -> DataFrame:
    """Convert raw event strings into the canonical market-price types."""
    return parsed_df.select(
        "_parse_valid",
        F.trim(F.col("ticker")).alias("ticker"),
        F.to_date(F.col("trading_date"), "yyyyMMdd").alias("trading_date"),
        F.col("open").cast("long").alias("open"),
        F.col("high").cast("long").alias("high"),
        F.col("low").cast("long").alias("low"),
        F.col("close").cast("long").alias("close"),
        F.col("volume").cast("long").alias("volume"),
        F.trim(F.col("source")).alias("source"),
        F.col("adjusted").cast("boolean").alias("adjusted"),
        "_kafka_partition",
        "_kafka_offset",
        "_kafka_timestamp",
    )


def required_fields_are_valid() -> Column:
    """Return the validation expression for required canonical fields."""
    condition = F.col("_parse_valid")

    for column_name in REQUIRED_COLUMNS:
        condition = condition & F.col(column_name).isNotNull()

    return condition & (F.length(F.col("ticker")) > 0) & (F.length(F.col("source")) > 0)


def ohlc_is_valid() -> Column:
    """Return the market-price domain validation expression."""
    return (
        (F.col("open") > 0)
        & (F.col("high") > 0)
        & (F.col("low") > 0)
        & (F.col("close") > 0)
        & (F.col("volume") >= 0)
        & (F.col("high") >= F.greatest("open", "low", "close"))
        & (F.col("low") <= F.least("open", "high", "close"))
    )


def deduplicate_market_prices(valid_df: DataFrame) -> DataFrame:
    """Keep the latest Kafka event for each ticker and trading date."""
    latest_event = Window.partitionBy("ticker", "trading_date").orderBy(
        F.col("_kafka_timestamp").desc_nulls_last(),
        F.col("_kafka_partition").desc(),
        F.col("_kafka_offset").desc(),
    )

    return (
        valid_df.withColumn("_dedup_rank", F.row_number().over(latest_event))
        .filter(F.col("_dedup_rank") == 1)
        .drop("_dedup_rank")
    )


def add_daily_return(deduplicated_df: DataFrame) -> DataFrame:
    """Calculate close-to-close return without using future observations."""
    chronological = Window.partitionBy("ticker").orderBy("trading_date")
    previous_close = F.lag("close").over(chronological)

    return deduplicated_df.withColumn(
        "daily_return",
        F.when(previous_close.isNull(), F.lit(None).cast("double")).otherwise(
            F.col("close").cast("double") / previous_close.cast("double") - F.lit(1.0)
        ),
    ).select(*FINAL_COLUMNS)


def run_batch(
    spark: SparkSession,
    bootstrap_servers: str,
    topic: str,
    output_path: str,
) -> None:
    """Read a bounded Kafka snapshot, normalize it, and write Silver Parquet."""
    kafka_df = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap_servers)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("endingOffsets", "latest")
        .load()
        .cache()
    )

    input_row_count = kafka_df.count()
    typed_df = normalize_types(parse_kafka_events(kafka_df)).cache()
    parsed_row_count = typed_df.filter(F.col("_parse_valid")).count()

    non_null_df = typed_df.filter(required_fields_are_valid()).cache()
    after_null_validation_count = non_null_df.count()

    valid_ohlc_df = non_null_df.filter(ohlc_is_valid()).cache()
    after_ohlc_validation_count = valid_ohlc_df.count()

    deduplicated_df = deduplicate_market_prices(valid_ohlc_df).cache()
    after_dedup_count = deduplicated_df.count()

    final_df = add_daily_return(deduplicated_df).cache()
    output_row_count = final_df.count()
    final_df.write.mode("overwrite").parquet(output_path)

    print(f"topic={topic}")
    print(f"input_row_count={input_row_count}")
    print(f"parsed_row_count={parsed_row_count}")
    print(f"null_or_type_invalid_count={input_row_count - after_null_validation_count}")
    print(f"ohlc_invalid_count={after_null_validation_count - after_ohlc_validation_count}")
    print(f"duplicate_removed_count={after_ohlc_validation_count - after_dedup_count}")
    print(f"output_row_count={output_row_count}")
    print(f"final_schema={final_df.schema.simpleString()}")
    print(f"output_path={output_path}")

    final_df.unpersist()
    deduplicated_df.unpersist()
    valid_ohlc_df.unpersist()
    non_null_df.unpersist()
    typed_df.unpersist()
    kafka_df.unpersist()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize the course Kafka market-price topic with Spark batch."
    )
    parser.add_argument("--bootstrap-servers", default=DEFAULT_BOOTSTRAP_SERVERS)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    spark = SparkSession.builder.appName("fair-value-market-price-batch").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    try:
        run_batch(
            spark=spark,
            bootstrap_servers=args.bootstrap_servers,
            topic=args.topic,
            output_path=args.output_path,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
