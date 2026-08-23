import polars as pl

CYCLE_INDICATORS = (
    "semiconductor_production_index",
    "semiconductor_shipment_index",
    "semiconductor_inventory_index",
)
FRED_CYCLE_INDICATORS = (
    "us_semiconductor_industrial_production",
    "us_semiconductor_capacity_utilization",
    "us_semiconductor_producer_price_index",
)


def derive_semiconductor_cycle_features(indicators: pl.DataFrame) -> pl.DataFrame:
    selected = _select_monthly_indicators(indicators, "kosis", CYCLE_INDICATORS)
    frame = _pivot_with_availability(selected).with_columns(
        (pl.col("period_end").dt.year() * 12 + pl.col("period_end").dt.month()).alias("_month")
    )
    has_year = pl.col("_month") - pl.col("_month").shift(12) == 12
    expressions = []
    for indicator in CYCLE_INDICATORS:
        expressions.append(
            pl.when(has_year)
            .then(pl.col(indicator) / pl.col(indicator).shift(12) - 1.0)
            .otherwise(None)
            .alias(indicator.replace("_index", "_yoy"))
        )
    return (
        frame.with_columns(
            *expressions,
            pl.when(pl.col("semiconductor_shipment_index") > 0)
            .then(pl.col("semiconductor_inventory_index") / pl.col("semiconductor_shipment_index"))
            .otherwise(None)
            .alias("semiconductor_inventory_shipment_ratio"),
        )
        .drop("_month")
        .sort("period_end")
    )


def derive_global_semiconductor_cycle_features(indicators: pl.DataFrame) -> pl.DataFrame:
    selected = _select_monthly_indicators(indicators, "fred", FRED_CYCLE_INDICATORS)
    frame = _pivot_with_availability(selected).with_columns(
        (pl.col("period_end").dt.year() * 12 + pl.col("period_end").dt.month()).alias("_month")
    )
    has_year = pl.col("_month") - pl.col("_month").shift(12) == 12
    return (
        frame.with_columns(
            pl.when(has_year)
            .then(
                pl.col("us_semiconductor_industrial_production")
                / pl.col("us_semiconductor_industrial_production").shift(12)
                - 1.0
            )
            .otherwise(None)
            .alias("us_semiconductor_industrial_production_yoy"),
            pl.when(has_year)
            .then(
                pl.col("us_semiconductor_producer_price_index")
                / pl.col("us_semiconductor_producer_price_index").shift(12)
                - 1.0
            )
            .otherwise(None)
            .alias("us_semiconductor_producer_price_index_yoy"),
            pl.when(has_year)
            .then(
                pl.col("us_semiconductor_capacity_utilization")
                - pl.col("us_semiconductor_capacity_utilization").shift(12)
            )
            .otherwise(None)
            .alias("us_semiconductor_capacity_utilization_yoy_change"),
        )
        .drop("_month")
        .sort("period_end")
    )


def _select_monthly_indicators(
    indicators: pl.DataFrame,
    source: str,
    indicator_ids: tuple[str, ...],
) -> pl.DataFrame:
    required = {"indicator_id", "period_end", "available_at", "value", "source"}
    missing = required - set(indicators.columns)
    if missing:
        raise ValueError(f"Missing canonical indicator columns: {sorted(missing)}")
    selected = indicators.filter(
        (pl.col("source") == source) & pl.col("indicator_id").is_in(indicator_ids)
    )
    present = set(selected.get_column("indicator_id").unique().to_list())
    if missing_indicators := set(indicator_ids) - present:
        raise ValueError(f"Missing cycle indicators: {sorted(missing_indicators)}")
    return selected


def _pivot_with_availability(selected: pl.DataFrame) -> pl.DataFrame:
    availability = selected.group_by("period_end").agg(
        pl.col("available_at").max().alias("available_at")
    )
    return (
        selected.pivot(
            on="indicator_id",
            index="period_end",
            values="value",
            aggregate_function="last",
        )
        .join(availability, on="period_end", how="left")
        .sort("period_end")
    )
