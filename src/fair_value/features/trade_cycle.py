from __future__ import annotations

import polars as pl

TRADE_CYCLE_FEATURE_COLUMNS = (
    "source",
    "reporter_code",
    "partner_code",
    "period_end",
    "available_at",
    "export_value_usd",
    "import_value_usd",
    "trade_balance_usd",
    "export_yoy",
    "import_yoy",
    "export_momentum_3m",
    "import_momentum_3m",
)


def derive_trade_cycle_features(trade_flows: pl.DataFrame) -> pl.DataFrame:
    """Aggregate selected HS codes into monthly trade-cycle signals."""
    required = {
        "source",
        "reporter_code",
        "partner_code",
        "flow_code",
        "hs_code",
        "period_end",
        "available_at",
        "trade_value_usd",
        "collected_at",
    }
    if missing := required - set(trade_flows.columns):
        raise ValueError(f"Missing canonical trade-flow columns: {sorted(missing)}")
    dimensions = [
        "source",
        "reporter_code",
        "partner_code",
        "flow_code",
        "hs_code",
        "period_end",
    ]
    latest = (
        trade_flows.sort([*dimensions, "available_at", "collected_at"])
        .unique(subset=dimensions, keep="last", maintain_order=True)
        .sort(dimensions)
    )
    grouped = latest.group_by(
        ["source", "reporter_code", "partner_code", "period_end", "flow_code"]
    ).agg(
        pl.col("trade_value_usd").sum(),
        pl.col("available_at").max(),
    )
    wide = grouped.pivot(
        on="flow_code",
        index=["source", "reporter_code", "partner_code", "period_end"],
        values="trade_value_usd",
        aggregate_function="first",
    )
    availability = grouped.group_by(["source", "reporter_code", "partner_code", "period_end"]).agg(
        pl.col("available_at").max()
    )
    wide = wide.join(
        availability,
        on=["source", "reporter_code", "partner_code", "period_end"],
        how="left",
    )
    for code in ("X", "M"):
        if code not in wide.columns:
            wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(code))

    keys = ["source", "reporter_code", "partner_code"]
    frame = (
        wide.rename({"X": "export_value_usd", "M": "import_value_usd"})
        .sort([*keys, "period_end"])
        .with_columns(
            (pl.col("period_end").dt.year() * 12 + pl.col("period_end").dt.month()).alias("_month")
        )
    )
    has_year = pl.col("_month") - pl.col("_month").shift(12).over(keys) == 12
    has_three_months = pl.col("_month") - pl.col("_month").shift(3).over(keys) == 3
    return (
        frame.with_columns(
            (
                pl.col("export_value_usd").fill_null(0) - pl.col("import_value_usd").fill_null(0)
            ).alias("trade_balance_usd"),
            pl.when(has_year)
            .then(pl.col("export_value_usd") / pl.col("export_value_usd").shift(12).over(keys) - 1)
            .otherwise(None)
            .alias("export_yoy"),
            pl.when(has_year)
            .then(pl.col("import_value_usd") / pl.col("import_value_usd").shift(12).over(keys) - 1)
            .otherwise(None)
            .alias("import_yoy"),
            pl.when(has_three_months)
            .then(pl.col("export_value_usd") / pl.col("export_value_usd").shift(3).over(keys) - 1)
            .otherwise(None)
            .alias("export_momentum_3m"),
            pl.when(has_three_months)
            .then(pl.col("import_value_usd") / pl.col("import_value_usd").shift(3).over(keys) - 1)
            .otherwise(None)
            .alias("import_momentum_3m"),
        )
        .select(TRADE_CYCLE_FEATURE_COLUMNS)
        .sort([*keys, "period_end"])
    )
