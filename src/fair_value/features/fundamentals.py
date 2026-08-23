from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from fair_value.features.share_basis import StockSplit, add_price_basis_share_features

FLOW_YTD_COLUMNS = (
    "revenue_ytd",
    "operating_income_ytd",
    "net_income_parent_ytd",
    "operating_cash_flow_ytd",
    "capex_ytd",
)


def derive_fundamental_features(
    financials: pl.DataFrame,
    stock_splits: Sequence[StockSplit] = (),
) -> pl.DataFrame:
    """Derive quarterly and trailing features using only currently reported rows."""
    required = {
        "ticker",
        "business_year",
        "report_quarter",
        "period_end",
        "available_at",
        "equity_parent",
        "inventories",
        "total_shares_outstanding",
        *FLOW_YTD_COLUMNS,
    }
    missing = required - set(financials.columns)
    if missing:
        raise ValueError(f"Missing canonical financial columns: {sorted(missing)}")

    frame = financials.sort(["ticker", "period_end"]).with_columns(
        (
            pl.col("business_year").cast(pl.Int32) * 4 + pl.col("report_quarter").cast(pl.Int32)
        ).alias("_quarter_index")
    )
    previous_year = pl.col("business_year").shift(1).over("ticker")
    previous_quarter = pl.col("report_quarter").shift(1).over("ticker")
    has_previous_ytd = (previous_year == pl.col("business_year")) & (
        previous_quarter == pl.col("report_quarter") - 1
    )

    quarter_expressions: list[pl.Expr] = []
    for column_name in FLOW_YTD_COLUMNS:
        quarter_column = column_name.removesuffix("_ytd") + "_quarter"
        previous_ytd = pl.col(column_name).shift(1).over("ticker")
        quarter_expressions.append(
            pl.when(pl.col("report_quarter") == 1)
            .then(pl.col(column_name))
            .when(has_previous_ytd)
            .then(pl.col(column_name) - previous_ytd)
            .otherwise(None)
            .cast(pl.Float64)
            .alias(quarter_column)
        )

    frame = frame.with_columns(quarter_expressions)
    current_index = pl.col("_quarter_index")
    index_three_rows_ago = current_index.shift(3).over("ticker")
    has_four_consecutive_quarters = current_index - index_three_rows_ago == 3

    ttm_expressions: list[pl.Expr] = []
    for column_name in FLOW_YTD_COLUMNS:
        base_name = column_name.removesuffix("_ytd")
        quarter_column = base_name + "_quarter"
        ttm_expressions.append(
            pl.when(has_four_consecutive_quarters)
            .then(pl.col(quarter_column).rolling_sum(window_size=4, min_samples=4).over("ticker"))
            .otherwise(None)
            .alias(base_name + "_ttm")
        )

    frame = frame.with_columns(ttm_expressions)
    beginning_equity = pl.col("equity_parent").shift(4).over("ticker")
    beginning_inventory = pl.col("inventories").shift(4).over("ticker")
    index_four_rows_ago = pl.col("_quarter_index").shift(4).over("ticker")
    has_year_ago = pl.col("_quarter_index") - index_four_rows_ago == 4
    average_equity = (pl.col("equity_parent") + beginning_equity) / 2.0

    frame = frame.with_columns(
        pl.when(has_year_ago & (average_equity > 0))
        .then(pl.col("net_income_parent_ttm") / average_equity)
        .otherwise(None)
        .alias("reported_roe_ttm"),
        pl.when(pl.col("revenue_ttm") != 0)
        .then(pl.col("operating_income_ttm") / pl.col("revenue_ttm"))
        .otherwise(None)
        .alias("operating_margin_ttm"),
        pl.when(pl.col("revenue_ttm") != 0)
        .then(pl.col("capex_ttm") / pl.col("revenue_ttm"))
        .otherwise(None)
        .alias("capex_to_revenue_ttm"),
        (pl.col("operating_cash_flow_ttm") - pl.col("capex_ttm")).alias("fcf_proxy_ttm"),
        pl.when(has_year_ago & beginning_inventory.is_not_null() & (beginning_inventory != 0))
        .then(pl.col("inventories") / beginning_inventory - 1.0)
        .otherwise(None)
        .alias("inventory_growth_yoy"),
        pl.when(pl.col("total_shares_outstanding") > 0)
        .then(
            pl.col("equity_parent").cast(pl.Float64)
            / pl.col("total_shares_outstanding").cast(pl.Float64)
        )
        .otherwise(None)
        .alias("equity_per_distributed_share"),
        pl.when(pl.col("total_shares_outstanding") > 0)
        .then(pl.col("net_income_parent_ttm") / pl.col("total_shares_outstanding").cast(pl.Float64))
        .otherwise(None)
        .alias("earnings_per_distributed_share_ttm"),
    )

    frame = add_price_basis_share_features(frame, stock_splits)
    return (
        frame.with_columns(
            pl.col("reported_roe_ttm")
            .rolling_median(window_size=20, min_samples=8)
            .over("ticker")
            .alias("roe_ttm_5y_median_candidate")
        )
        .drop("_quarter_index")
        .sort(["ticker", "period_end"])
    )
