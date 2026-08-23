from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl

from fair_value.collectors.ecos.client import EcosClient
from fair_value.collectors.ecos.statistics import collect_ecos_indicator
from fair_value.collectors.fred.client import FredClient
from fair_value.collectors.fred.statistics import collect_fred_indicator
from fair_value.collectors.kosis.client import KosisClient
from fair_value.collectors.kosis.statistics import collect_kosis_indicator
from fair_value.config_loader import load_cycle_indicators
from fair_value.features.cycle import (
    derive_global_semiconductor_cycle_features,
    derive_semiconductor_cycle_features,
)
from fair_value.normalization.economic_indicators import (
    EconomicIndicatorQualityReport,
    normalize_economic_indicators,
)
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

BRONZE_ROOTS = (
    PROJECT_ROOT / "data" / "bronze" / "ecos" / "statistics",
    PROJECT_ROOT / "data" / "bronze" / "kosis" / "statistics",
    PROJECT_ROOT / "data" / "bronze" / "fred" / "statistics",
)
SILVER_PATH = PROJECT_ROOT / "data" / "silver" / "economic_indicators" / "canonical.parquet"
FEATURE_PATH = PROJECT_ROOT / "data" / "gold" / "features" / "semiconductor_cycle_features.parquet"
GLOBAL_FEATURE_PATH = (
    PROJECT_ROOT / "data" / "gold" / "features" / "global_semiconductor_cycle_features.parquet"
)


def load_documents(roots: Sequence[Path] = BRONZE_ROOTS) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for root in roots:
        for path in sorted(root.glob("*/*.json")):
            with path.open("r", encoding="utf-8") as file:
                payload: object = json.load(file)
            if not isinstance(payload, dict):
                raise ValueError(f"Economic Bronze document must be an object: {path}")
            documents.append(cast(dict[str, object], payload))
    if not documents:
        raise ValueError("No ECOS, KOSIS, or FRED Bronze documents were found")
    return documents


def collect_sources(
    ecos_start_date: date,
    kosis_start_date: date,
    fred_start_date: date,
    end_date: date,
) -> None:
    config = load_cycle_indicators()
    start_day = ecos_start_date.strftime("%Y%m%d")
    start_month = kosis_start_date.strftime("%Y%m")
    start_iso = fred_start_date.isoformat()
    end_day = end_date.strftime("%Y%m%d")
    end_month = end_date.strftime("%Y%m")
    end_iso = end_date.isoformat()

    with EcosClient() as client:
        for indicator_id, ecos_indicator in config.ecos.items():
            path, count = collect_ecos_indicator(
                client,
                indicator_id,
                ecos_indicator,
                max(start_day, ecos_indicator.start_period),
                end_day,
            )
            print(f"source=ecos indicator={indicator_id} rows={count} path={path}")

    with KosisClient() as client:
        for indicator_id, kosis_indicator in config.kosis.items():
            path, count = collect_kosis_indicator(
                client,
                indicator_id,
                kosis_indicator,
                max(start_month, kosis_indicator.start_period),
                end_month,
            )
            print(f"source=kosis indicator={indicator_id} rows={count} path={path}")

    with FredClient() as client:
        for indicator_id, fred_indicator in config.fred.items():
            path, count = collect_fred_indicator(
                client,
                indicator_id,
                fred_indicator,
                max(start_iso, fred_indicator.start_period),
                end_iso,
            )
            print(f"source=fred indicator={indicator_id} rows={count} path={path}")


def resolve_start_dates(
    mode: str,
    requested_start: date | None,
) -> tuple[date, date, date]:
    """Use source-specific lookbacks to capture late updates and revisions."""
    historical_start = requested_start or date(2015, 1, 1)
    if mode == "historical" or not SILVER_PATH.exists():
        return historical_start, historical_start, historical_start

    frame = pl.read_parquet(SILVER_PATH)
    return (
        _source_start(frame, "ecos", historical_start, 7),
        _source_start(frame, "kosis", historical_start, 62),
        _source_start(frame, "fred", historical_start, 62),
    )


def _source_start(
    frame: pl.DataFrame,
    source: str,
    fallback: date,
    lookback_days: int,
) -> date:
    latest = frame.filter(pl.col("source") == source).select(pl.col("period_end").max()).item()
    if not isinstance(latest, date):
        return fallback
    return latest - timedelta(days=lookback_days)


def print_quality(report: EconomicIndicatorQualityReport) -> None:
    print(f"input_row_count={report.input_row_count}")
    print(f"invalid_value_count={report.invalid_value_count}")
    print(f"duplicate_removed_count={report.duplicate_removed_count}")
    print(f"output_row_count={report.output_row_count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and normalize ECOS/KOSIS/FRED economic indicators."
    )
    parser.add_argument("--mode", choices=("historical", "incremental"), default="incremental")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--skip-collect", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    end_date = args.end_date or datetime.now(ZoneInfo("Asia/Seoul")).date()
    ecos_start, kosis_start, fred_start = resolve_start_dates(args.mode, args.start_date)
    if any(start > end_date for start in (ecos_start, kosis_start, fred_start)):
        raise ValueError("resolved start date must not be later than end-date")
    if not args.skip_collect:
        print(
            f"ecos_start_date={ecos_start} kosis_start_date={kosis_start} "
            f"fred_start_date={fred_start}"
        )
        collect_sources(ecos_start, kosis_start, fred_start, end_date)

    indicators, report = normalize_economic_indicators(load_documents())
    features = derive_semiconductor_cycle_features(indicators)
    global_features = derive_global_semiconductor_cycle_features(indicators)
    silver_path = write_parquet_atomic(indicators, SILVER_PATH)
    feature_path = write_parquet_atomic(features, FEATURE_PATH)
    global_feature_path = write_parquet_atomic(global_features, GLOBAL_FEATURE_PATH)
    print_quality(report)
    print(f"silver_schema={indicators.schema}")
    print(f"cycle_feature_row_count={features.height}")
    print(f"global_cycle_feature_row_count={global_features.height}")
    print(f"silver_path={silver_path}")
    print(f"feature_path={feature_path}")
    print(f"global_feature_path={global_feature_path}")


if __name__ == "__main__":
    main()
