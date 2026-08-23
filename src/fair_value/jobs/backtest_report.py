from __future__ import annotations

import polars as pl

from fair_value.backtest.report import (
    build_backtest_summary,
    combine_backtest_results,
    select_non_overlapping_horizons,
)
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

BACKTEST_ROOT = PROJECT_ROOT / "data" / "gold" / "backtest"
BENCHMARK_PATH = BACKTEST_ROOT / "benchmark_future_returns.parquet"
CYCLE_PATH = BACKTEST_ROOT / "cycle_rim_future_returns.parquet"
REPORT_ROOT = BACKTEST_ROOT / "reports"
COMBINED_PATH = REPORT_ROOT / "combined_results.parquet"
BY_TICKER_PATH = REPORT_ROOT / "summary_by_ticker_horizon.parquet"
BY_YEAR_PATH = REPORT_ROOT / "summary_by_year_horizon.parquet"
BY_TICKER_YEAR_PATH = REPORT_ROOT / "summary_by_ticker_year_horizon.parquet"
NON_OVERLAPPING_RESULTS_PATH = REPORT_ROOT / "non_overlapping_results.parquet"
NON_OVERLAPPING_SUMMARY_PATH = REPORT_ROOT / "summary_non_overlapping.parquet"


def build_backtest_reports() -> dict[str, pl.DataFrame]:
    combined = combine_backtest_results(
        pl.read_parquet(BENCHMARK_PATH),
        pl.read_parquet(CYCLE_PATH),
    )
    non_overlapping = select_non_overlapping_horizons(combined)
    return {
        "combined": combined,
        "by_ticker": build_backtest_summary(
            combined,
            group_columns=("model_name", "ticker", "horizon_months"),
        ),
        "by_year": build_backtest_summary(
            combined,
            group_columns=("model_name", "valuation_year", "horizon_months"),
        ),
        "by_ticker_year": build_backtest_summary(
            combined,
            group_columns=(
                "model_name",
                "ticker",
                "valuation_year",
                "horizon_months",
            ),
        ),
        "non_overlapping_results": non_overlapping,
        "non_overlapping_summary": build_backtest_summary(
            non_overlapping,
            group_columns=("model_name", "ticker", "horizon_months"),
        ),
    }


def main() -> None:
    reports = build_backtest_reports()
    output_paths = {
        "combined": COMBINED_PATH,
        "by_ticker": BY_TICKER_PATH,
        "by_year": BY_YEAR_PATH,
        "by_ticker_year": BY_TICKER_YEAR_PATH,
        "non_overlapping_results": NON_OVERLAPPING_RESULTS_PATH,
        "non_overlapping_summary": NON_OVERLAPPING_SUMMARY_PATH,
    }
    for name, frame in reports.items():
        path = write_parquet_atomic(frame, output_paths[name])
        print(f"report={name} rows={frame.height} output_path={path}")

    print(
        reports["non_overlapping_summary"].select(
            "model_name",
            "ticker",
            "horizon_months",
            "evaluated_rows",
            "pending_rows",
            "value_to_price_return_correlation",
            "range_coverage",
        )
    )


if __name__ == "__main__":
    main()
