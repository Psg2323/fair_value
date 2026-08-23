from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl

from fair_value.features.share_basis import StockSplit, validate_stock_split_coverage

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class QualityCheck:
    name: str
    violation_count: int
    severity: Severity = "error"


@dataclass(frozen=True, slots=True)
class DatasetQualityReport:
    dataset: str
    row_count: int
    checks: tuple[QualityCheck, ...]

    @property
    def error_count(self) -> int:
        return sum(check.violation_count for check in self.checks if check.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(check.violation_count for check in self.checks if check.severity == "warning")

    def assert_passed(self) -> None:
        failed = {
            check.name: check.violation_count
            for check in self.checks
            if check.severity == "error" and check.violation_count > 0
        }
        if failed:
            raise ValueError(f"{self.dataset} quality gate failed: {failed}")


def validate_market_prices(frame: pl.DataFrame) -> DatasetQualityReport:
    required = {
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
    }
    _require_columns(frame, required, "market_price")

    expected_return = (
        pl.col("close").cast(pl.Float64) / pl.col("close").shift(1).over("ticker").cast(pl.Float64)
        - 1.0
    )
    audited = frame.sort(["ticker", "trading_date"]).with_columns(
        expected_return.alias("_expected_return")
    )
    return_mismatch = audited.filter(
        (pl.col("_expected_return").is_null() != pl.col("daily_return").is_null())
        | (
            pl.col("_expected_return").is_not_null()
            & pl.col("daily_return").is_not_null()
            & ((pl.col("_expected_return") - pl.col("daily_return")).abs() > 1e-12)
        )
    ).height
    required_without_return = required - {"daily_return"}
    null_count = frame.filter(
        pl.any_horizontal([pl.col(column).is_null() for column in required_without_return])
    ).height
    ohlc_invalid = frame.filter(
        (pl.col("open") <= 0)
        | (pl.col("high") <= 0)
        | (pl.col("low") <= 0)
        | (pl.col("close") <= 0)
        | (pl.col("volume") < 0)
        | (pl.col("high") < pl.max_horizontal("open", "low", "close"))
        | (pl.col("low") > pl.min_horizontal("open", "high", "close"))
    ).height
    adjusted_basis_invalid = frame.filter(pl.col("adjusted").is_null() | ~pl.col("adjusted")).height

    return DatasetQualityReport(
        dataset="market_price",
        row_count=frame.height,
        checks=(
            QualityCheck(
                "duplicate_ticker_trading_date",
                _duplicate_count(frame, ["ticker", "trading_date"]),
            ),
            QualityCheck("required_nulls", null_count),
            QualityCheck("invalid_ohlcv", ohlc_invalid),
            QualityCheck("non_adjusted_price_basis", adjusted_basis_invalid),
            QualityCheck("daily_return_mismatch", return_mismatch),
        ),
    )


def validate_financials(
    frame: pl.DataFrame,
    stock_splits: tuple[StockSplit, ...],
) -> DatasetQualityReport:
    required = {
        "ticker",
        "period_end",
        "available_at",
        "report_code",
        "equity_parent",
        "net_income_parent_ytd",
        "total_shares_outstanding",
    }
    _require_columns(frame, required, "financials")
    validate_stock_split_coverage(frame, stock_splits)

    return DatasetQualityReport(
        dataset="financials",
        row_count=frame.height,
        checks=(
            QualityCheck(
                "duplicate_ticker_period_report",
                _duplicate_count(frame, ["ticker", "period_end", "report_code"]),
            ),
            QualityCheck(
                "period_after_availability",
                frame.filter(pl.col("period_end") > pl.col("available_at")).height,
            ),
            QualityCheck(
                "nonpositive_share_count",
                frame.filter(pl.col("total_shares_outstanding") <= 0).height,
            ),
            QualityCheck(
                "missing_share_count",
                frame.filter(pl.col("total_shares_outstanding").is_null()).height,
                "warning",
            ),
        ),
    )


def validate_fundamental_features(frame: pl.DataFrame) -> DatasetQualityReport:
    required = {
        "ticker",
        "period_end",
        "total_shares_outstanding",
        "equity_parent",
        "net_income_parent_ttm",
        "price_basis_share_adjustment_factor",
        "price_basis_total_shares_outstanding",
        "equity_per_price_basis_share",
        "earnings_per_price_basis_share_ttm",
    }
    _require_columns(frame, required, "fundamental_features")

    expected_shares = pl.col("total_shares_outstanding").cast(pl.Float64) * pl.col(
        "price_basis_share_adjustment_factor"
    )
    expected_equity_per_share = pl.col("equity_parent").cast(pl.Float64) / pl.col(
        "price_basis_total_shares_outstanding"
    )
    expected_earnings_per_share = pl.col("net_income_parent_ttm").cast(pl.Float64) / pl.col(
        "price_basis_total_shares_outstanding"
    )
    audited = frame.with_columns(
        expected_shares.alias("_expected_price_basis_shares"),
        expected_equity_per_share.alias("_expected_equity_per_share"),
        expected_earnings_per_share.alias("_expected_earnings_per_share"),
    )
    share_basis_mismatch = audited.filter(
        _float_mismatch(
            "_expected_price_basis_shares",
            "price_basis_total_shares_outstanding",
        )
    ).height
    equity_per_share_mismatch = audited.filter(
        _float_mismatch(
            "_expected_equity_per_share",
            "equity_per_price_basis_share",
        )
    ).height
    earnings_per_share_mismatch = audited.filter(
        _float_mismatch(
            "_expected_earnings_per_share",
            "earnings_per_price_basis_share_ttm",
        )
    ).height

    return DatasetQualityReport(
        dataset="fundamental_features",
        row_count=frame.height,
        checks=(
            QualityCheck(
                "nonpositive_share_adjustment_factor",
                frame.filter(pl.col("price_basis_share_adjustment_factor") <= 0).height,
            ),
            QualityCheck("price_basis_share_mismatch", share_basis_mismatch),
            QualityCheck("equity_per_share_mismatch", equity_per_share_mismatch),
            QualityCheck("earnings_per_share_mismatch", earnings_per_share_mismatch),
            QualityCheck(
                "missing_price_basis_share_count",
                frame.filter(pl.col("price_basis_total_shares_outstanding").is_null()).height,
                "warning",
            ),
        ),
    )


def validate_economic_indicators(frame: pl.DataFrame) -> DatasetQualityReport:
    required = {
        "source",
        "indicator_id",
        "period_end",
        "available_at",
        "value",
    }
    _require_columns(frame, required, "economic_indicators")
    return DatasetQualityReport(
        dataset="economic_indicators",
        row_count=frame.height,
        checks=(
            QualityCheck(
                "duplicate_source_indicator_period",
                _duplicate_count(
                    frame,
                    ["source", "indicator_id", "period_end"],
                ),
            ),
            QualityCheck(
                "period_after_availability",
                frame.filter(pl.col("period_end") > pl.col("available_at")).height,
            ),
            QualityCheck(
                "missing_value",
                frame.filter(pl.col("value").is_null()).height,
            ),
        ),
    )


def validate_asof_dataset(frame: pl.DataFrame) -> DatasetQualityReport:
    required = {
        "ticker",
        "valuation_date",
        "market_price",
        "financial_period_end",
        "financial_available_at",
    }
    _require_columns(frame, required, "valuation_asof")
    availability_columns = [column for column in frame.columns if column.endswith("_available_at")]
    availability_violations = sum(
        frame.filter(
            pl.col(column).is_not_null() & (pl.col(column) > pl.col("valuation_date"))
        ).height
        for column in availability_columns
    )
    return DatasetQualityReport(
        dataset="valuation_asof",
        row_count=frame.height,
        checks=(
            QualityCheck(
                "duplicate_ticker_valuation_date",
                _duplicate_count(frame, ["ticker", "valuation_date"]),
            ),
            QualityCheck(
                "nonpositive_market_price",
                frame.filter(pl.col("market_price") <= 0).height,
            ),
            QualityCheck(
                "future_financial_period",
                frame.filter(pl.col("financial_period_end") > pl.col("valuation_date")).height,
            ),
            QualityCheck("future_availability", availability_violations),
        ),
    )


def _require_columns(
    frame: pl.DataFrame,
    required: set[str],
    dataset: str,
) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{dataset} missing required columns: {sorted(missing)}")


def _duplicate_count(frame: pl.DataFrame, subset: list[str]) -> int:
    return frame.height - frame.unique(subset=subset).height


def _float_mismatch(expected: str, actual: str) -> pl.Expr:
    return (pl.col(expected).is_null() != pl.col(actual).is_null()) | (
        pl.col(expected).is_not_null()
        & pl.col(actual).is_not_null()
        & ((pl.col(expected) - pl.col(actual)).abs() > 1e-9)
    )
