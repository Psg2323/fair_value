from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl

from fair_value.collectors.kis.client import KISClient
from fair_value.collectors.kis.daily_prices import collect_daily_prices
from fair_value.config_loader import load_companies
from fair_value.normalization.market_price import (
    MarketPriceQualityReport,
    normalize_kis_documents,
)
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

BRONZE_ROOT = PROJECT_ROOT / "data" / "bronze" / "kis" / "daily_prices"
SILVER_DIRECTORY = PROJECT_ROOT / "data" / "silver" / "market_price"
SILVER_PATH = SILVER_DIRECTORY / "canonical.parquet"
KST = ZoneInfo("Asia/Seoul")
MARKET_PRICE_READY_TIME = time(16, 10)


def load_kis_bronze_documents(root: Path = BRONZE_ROOT) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []

    for path in sorted(root.glob("*/*.json")):
        with path.open("r", encoding="utf-8") as file:
            raw_document: object = json.load(file)

        if not isinstance(raw_document, dict):
            raise ValueError(f"KIS Bronze document must be an object: {path}")

        documents.append(cast(dict[str, object], raw_document))

    if not documents:
        raise ValueError(f"No KIS Bronze documents found under {root}")

    return documents


def write_canonical_market_price(
    frame: pl.DataFrame,
    output_path: Path = SILVER_PATH,
) -> Path:
    return write_parquet_atomic(frame, output_path)


def build_canonical_market_price() -> tuple[pl.DataFrame, MarketPriceQualityReport, Path]:
    documents = load_kis_bronze_documents()
    frame, report = normalize_kis_documents(documents)
    output_path = write_canonical_market_price(frame)
    return frame, report, output_path


def collect_incremental_prices(
    frame: pl.DataFrame,
    end_date: date,
    bootstrap_start_date: date = date(2015, 1, 1),
) -> list[tuple[str, date, date, int]]:
    companies = load_companies()
    results: list[tuple[str, date, date, int]] = []

    with KISClient() as client:
        for company in companies.companies.values():
            if not company.enabled:
                continue

            ticker_rows = frame.filter(pl.col("ticker") == company.ticker)
            latest_value = ticker_rows.select(pl.col("trading_date").max()).item()
            start_date = (
                latest_value + timedelta(days=1)
                if isinstance(latest_value, date)
                else bootstrap_start_date
            )

            if start_date > end_date:
                results.append((company.ticker, start_date, end_date, 0))
                continue

            _, records = collect_daily_prices(
                client=client,
                ticker=company.ticker,
                start_date=start_date,
                end_date=end_date,
            )
            results.append((company.ticker, start_date, end_date, len(records)))

    return results


def print_quality_report(
    frame: pl.DataFrame,
    report: MarketPriceQualityReport,
    output_path: Path,
) -> None:
    print(f"input_row_count={report.input_row_count}")
    print(f"null_or_type_invalid_count={report.null_or_type_invalid_count}")
    print(f"ohlc_invalid_count={report.ohlc_invalid_count}")
    print(f"duplicate_removed_count={report.duplicate_removed_count}")
    print(f"output_row_count={report.output_row_count}")
    print(f"output_path={output_path}")
    print(f"schema={frame.schema}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or increment the canonical local market-price Silver dataset."
    )
    parser.add_argument(
        "--mode",
        choices=("historical", "incremental"),
        default="incremental",
    )
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument(
        "--bootstrap-start-date",
        type=date.fromisoformat,
        default=date(2015, 1, 1),
        help="First date collected for an enabled ticker missing from Silver.",
    )
    return parser


def resolve_incremental_end_date(
    requested_end: date | None,
    now: datetime | None = None,
) -> date:
    """Return the latest date whose closing price may be treated as complete."""
    if requested_end is not None:
        return requested_end
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = current.astimezone(KST)
    if local_now.time().replace(tzinfo=None) < MARKET_PRICE_READY_TIME:
        return local_now.date() - timedelta(days=1)
    return local_now.date()


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    frame, report, output_path = build_canonical_market_price()

    if args.mode == "incremental":
        end_date = resolve_incremental_end_date(args.end_date)
        incremental_results = collect_incremental_prices(
            frame,
            end_date,
            bootstrap_start_date=args.bootstrap_start_date,
        )

        for ticker, start_date, requested_end, record_count in incremental_results:
            print(
                f"ticker={ticker} start_date={start_date} "
                f"end_date={requested_end} collected_count={record_count}"
            )

        if any(record_count > 0 for *_, record_count in incremental_results):
            frame, report, output_path = build_canonical_market_price()

    print_quality_report(frame, report, output_path)


if __name__ == "__main__":
    main()
