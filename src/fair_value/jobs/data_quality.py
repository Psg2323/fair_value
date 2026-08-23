from __future__ import annotations

import argparse
from collections.abc import Sequence

import polars as pl

from fair_value.jobs._corporate_actions import load_stock_splits
from fair_value.quality.datasets import (
    DatasetQualityReport,
    validate_asof_dataset,
    validate_economic_indicators,
    validate_financials,
    validate_fundamental_features,
    validate_market_prices,
)
from fair_value.settings import PROJECT_ROOT

MARKET_PATH = PROJECT_ROOT / "data" / "silver" / "market_price" / "canonical.parquet"
FINANCIAL_PATH = PROJECT_ROOT / "data" / "silver" / "financials" / "canonical.parquet"
ECONOMIC_PATH = PROJECT_ROOT / "data" / "silver" / "economic_indicators" / "canonical.parquet"
FUNDAMENTAL_PATH = PROJECT_ROOT / "data" / "gold" / "features" / "fundamental_features.parquet"
ASOF_PATH = PROJECT_ROOT / "data" / "gold" / "model_inputs" / "valuation_asof_monthly.parquet"


def run_canonical_quality() -> tuple[DatasetQualityReport, ...]:
    stock_splits = load_stock_splits()
    return (
        validate_market_prices(pl.read_parquet(MARKET_PATH)),
        validate_financials(pl.read_parquet(FINANCIAL_PATH), stock_splits),
        validate_fundamental_features(pl.read_parquet(FUNDAMENTAL_PATH)),
        validate_economic_indicators(pl.read_parquet(ECONOMIC_PATH)),
    )


def run_asof_quality() -> tuple[DatasetQualityReport, ...]:
    return (validate_asof_dataset(pl.read_parquet(ASOF_PATH)),)


def print_report(report: DatasetQualityReport) -> None:
    print(
        f"dataset={report.dataset} rows={report.row_count} "
        f"errors={report.error_count} warnings={report.warning_count}"
    )
    for check in report.checks:
        print(
            f"dataset={report.dataset} check={check.name} "
            f"severity={check.severity} violations={check.violation_count}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate local canonical or as-of datasets.")
    parser.add_argument(
        "--scope",
        choices=("canonical", "asof", "all"),
        default="all",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    scope = build_parser().parse_args(argv).scope
    reports: tuple[DatasetQualityReport, ...] = ()
    if scope in {"canonical", "all"}:
        reports += run_canonical_quality()
    if scope in {"asof", "all"}:
        reports += run_asof_quality()

    for report in reports:
        print_report(report)
        report.assert_passed()


if __name__ == "__main__":
    main()
