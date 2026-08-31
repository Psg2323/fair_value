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
from fair_value.collectors.kis.minute_prices import collect_minute_prices
from fair_value.config_loader import load_companies
from fair_value.features.market_snapshot import attach_valuation_gap
from fair_value.features.market_state import derive_daily_market_state
from fair_value.normalization.minute_price import (
    MinutePriceQualityReport,
    normalize_kis_minute_documents,
)
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

KST = ZoneInfo("Asia/Seoul")
READY_TIME = time(16, 20)
BRONZE_ROOT = PROJECT_ROOT / "data" / "bronze" / "kis" / "minute_prices"
SILVER_PATH = PROJECT_ROOT / "data" / "silver" / "market_price_minute" / "canonical.parquet"
FEATURE_PATH = PROJECT_ROOT / "data" / "gold" / "features" / "market_state_daily.parquet"
FAIR_VALUE_PATH = PROJECT_ROOT / "data" / "gold" / "valuation" / "fair_value_range.parquet"
GAP_PATH = PROJECT_ROOT / "data" / "gold" / "market_state" / "daily_valuation_gap.parquet"


def resolve_target_date(
    requested: date | None,
    now: datetime | None = None,
) -> date:
    if requested is not None:
        return requested
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = current.astimezone(KST)
    if local_now.time().replace(tzinfo=None) < READY_TIME:
        return local_now.date() - timedelta(days=1)
    return local_now.date()


def collect_universe(target_date: date) -> list[tuple[str, int, Path]]:
    results: list[tuple[str, int, Path]] = []
    with KISClient() as client:
        for company in load_companies().companies.values():
            if not company.enabled:
                continue
            path, rows = collect_minute_prices(client, company.ticker, target_date)
            results.append((company.ticker, len(rows), path))
    return results


def load_bronze_documents(root: Path = BRONZE_ROOT) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for path in sorted(root.glob("*/*.json")):
        with path.open(encoding="utf-8") as handle:
            payload: object = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"KIS minute Bronze document must be an object: {path}")
        documents.append(cast(dict[str, object], payload))
    if not documents:
        raise ValueError(f"No KIS minute Bronze documents found under {root}")
    return documents


def build_outputs(
    documents: list[dict[str, object]],
) -> tuple[pl.DataFrame, pl.DataFrame, MinutePriceQualityReport]:
    minute_prices, report = normalize_kis_minute_documents(documents)
    features = derive_daily_market_state(minute_prices)
    return minute_prices, features, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect 20-stock KIS minute prices and build market-state features."
    )
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--skip-collect", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    target_date = resolve_target_date(args.target_date)
    if not args.skip_collect:
        for ticker, count, path in collect_universe(target_date):
            print(
                f"ticker={ticker} trading_date={target_date} "
                f"collected_count={count} bronze_path={path}"
            )

    minute_prices, features, report = build_outputs(load_bronze_documents())
    silver_path = write_parquet_atomic(minute_prices, SILVER_PATH)
    feature_path = write_parquet_atomic(features, FEATURE_PATH)
    print(f"input_row_count={report.input_row_count}")
    print(f"invalid_row_count={report.null_or_type_invalid_count}")
    print(f"duplicate_removed_count={report.duplicate_removed_count}")
    print(f"silver_row_count={minute_prices.height}")
    print(f"feature_row_count={features.height}")
    print(f"silver_path={silver_path}")
    print(f"feature_path={feature_path}")
    print(f"silver_schema={minute_prices.schema}")

    if FAIR_VALUE_PATH.exists():
        gaps = attach_valuation_gap(features, pl.read_parquet(FAIR_VALUE_PATH))
        gap_path = write_parquet_atomic(gaps, GAP_PATH)
        print(f"valuation_gap_row_count={gaps.height}")
        print(f"valuation_gap_available_count={gaps['fair_value_base'].is_not_null().sum()}")
        print(f"valuation_gap_path={gap_path}")


if __name__ == "__main__":
    main()
