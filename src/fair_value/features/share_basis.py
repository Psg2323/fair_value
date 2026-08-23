from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import isclose, isfinite, prod
from typing import cast

import polars as pl


@dataclass(frozen=True, slots=True)
class StockSplit:
    """A sourced unit conversion from reported shares to adjusted-price shares."""

    ticker: str
    effective_date: date
    share_multiplier: float

    def __post_init__(self) -> None:
        if not self.ticker:
            raise ValueError("ticker must not be empty")
        if not isfinite(self.share_multiplier):
            raise ValueError("share_multiplier must be finite")
        if self.share_multiplier <= 0 or self.share_multiplier == 1:
            raise ValueError("share_multiplier must be positive and different from one")


@dataclass(frozen=True, slots=True)
class ShareCountJump:
    ticker: str
    previous_period_end: date
    current_period_end: date
    previous_shares: float
    current_shares: float
    ratio: float


def add_price_basis_share_features(
    frame: pl.DataFrame,
    stock_splits: Sequence[StockSplit],
) -> pl.DataFrame:
    """Align reported per-share financials with the ex-post adjusted KIS price unit."""
    required = {
        "ticker",
        "period_end",
        "total_shares_outstanding",
        "equity_parent",
        "net_income_parent_ttm",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing price-basis input columns: {sorted(missing)}")

    factor = pl.lit(1.0)
    for split in sorted(stock_splits, key=lambda item: (item.ticker, item.effective_date)):
        factor *= (
            pl.when(
                (pl.col("ticker") == split.ticker)
                & (pl.col("period_end") < pl.lit(split.effective_date))
            )
            .then(pl.lit(split.share_multiplier))
            .otherwise(pl.lit(1.0))
        )

    adjusted = frame.with_columns(factor.alias("price_basis_share_adjustment_factor")).with_columns(
        (
            pl.col("total_shares_outstanding").cast(pl.Float64)
            * pl.col("price_basis_share_adjustment_factor")
        ).alias("price_basis_total_shares_outstanding")
    )
    return adjusted.with_columns(
        pl.when(pl.col("price_basis_total_shares_outstanding") > 0)
        .then(
            pl.col("equity_parent").cast(pl.Float64)
            / pl.col("price_basis_total_shares_outstanding")
        )
        .otherwise(None)
        .alias("equity_per_price_basis_share"),
        pl.when(pl.col("price_basis_total_shares_outstanding") > 0)
        .then(
            pl.col("net_income_parent_ttm").cast(pl.Float64)
            / pl.col("price_basis_total_shares_outstanding")
        )
        .otherwise(None)
        .alias("earnings_per_price_basis_share_ttm"),
    )


def detect_material_share_count_jumps(
    financials: pl.DataFrame,
    *,
    minimum_ratio: float = 1.5,
) -> tuple[ShareCountJump, ...]:
    """Find large adjacent-period changes that require an explicit explanation."""
    if minimum_ratio <= 1:
        raise ValueError("minimum_ratio must be greater than one")
    required = {"ticker", "period_end", "total_shares_outstanding"}
    missing = required - set(financials.columns)
    if missing:
        raise ValueError(f"Missing share-count audit columns: {sorted(missing)}")

    jumps = (
        financials.select(
            pl.col("ticker").cast(pl.String),
            pl.col("period_end").cast(pl.Date),
            pl.col("total_shares_outstanding").cast(pl.Float64),
        )
        .filter(pl.col("total_shares_outstanding") > 0)
        .sort(["ticker", "period_end"])
        .with_columns(
            pl.col("period_end").shift(1).over("ticker").alias("_previous_period_end"),
            pl.col("total_shares_outstanding").shift(1).over("ticker").alias("_previous_shares"),
        )
        .with_columns(
            (pl.col("total_shares_outstanding") / pl.col("_previous_shares")).alias("_ratio")
        )
        .filter((pl.col("_ratio") >= minimum_ratio) | (pl.col("_ratio") <= 1.0 / minimum_ratio))
    )

    return tuple(
        ShareCountJump(
            ticker=cast(str, row["ticker"]),
            previous_period_end=cast(date, row["_previous_period_end"]),
            current_period_end=cast(date, row["period_end"]),
            previous_shares=cast(float, row["_previous_shares"]),
            current_shares=cast(float, row["total_shares_outstanding"]),
            ratio=cast(float, row["_ratio"]),
        )
        for row in jumps.iter_rows(named=True)
    )


def validate_stock_split_coverage(
    financials: pl.DataFrame,
    stock_splits: Sequence[StockSplit],
    *,
    minimum_ratio: float = 1.5,
    relative_tolerance: float = 0.02,
) -> tuple[ShareCountJump, ...]:
    """Require every material share-count jump to match configured split actions."""
    jumps = detect_material_share_count_jumps(financials, minimum_ratio=minimum_ratio)
    uncovered: list[ShareCountJump] = []

    for jump in jumps:
        matching = [
            split
            for split in stock_splits
            if split.ticker == jump.ticker
            and jump.previous_period_end < split.effective_date <= jump.current_period_end
        ]
        expected_ratio = prod(split.share_multiplier for split in matching)
        if not matching or not isclose(
            jump.ratio,
            expected_ratio,
            rel_tol=relative_tolerance,
        ):
            uncovered.append(jump)

    if uncovered:
        details = [
            (
                jump.ticker,
                jump.previous_period_end.isoformat(),
                jump.current_period_end.isoformat(),
                round(jump.ratio, 6),
            )
            for jump in uncovered
        ]
        raise ValueError(f"Uncovered material share-count jumps: {details}")
    return jumps
