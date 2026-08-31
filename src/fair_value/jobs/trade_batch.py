from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from fair_value.collectors.comtrade.client import ComtradeClient
from fair_value.collectors.comtrade.statistics import collect_comtrade_monthly
from fair_value.collectors.customs.client import CustomsClient
from fair_value.collectors.customs.statistics import collect_customs_trade
from fair_value.config_loader import TradeIndicatorsConfig, load_trade_indicators
from fair_value.features.trade_cycle import derive_trade_cycle_features
from fair_value.normalization.trade_flows import (
    TradeFlowQualityReport,
    normalize_trade_documents,
)
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

KST = ZoneInfo("Asia/Seoul")
BRONZE_ROOTS = (
    PROJECT_ROOT / "data" / "bronze" / "customs" / "item_trade",
    PROJECT_ROOT / "data" / "bronze" / "un_comtrade" / "monthly_trade",
)
SILVER_PATH = PROJECT_ROOT / "data" / "silver" / "trade_flows" / "canonical.parquet"
FEATURE_PATH = PROJECT_ROOT / "data" / "gold" / "features" / "trade_cycle_features.parquet"


def month_periods(start_date: date, end_date: date) -> list[str]:
    if start_date > end_date:
        raise ValueError("start_date must not be later than end_date")
    periods: list[str] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        periods.append(f"{year:04d}{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return periods


def periods_by_year(periods: Sequence[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    for period in periods:
        if not chunks or chunks[-1][0][:4] != period[:4]:
            chunks.append([])
        chunks[-1].append(period)
    return chunks


def subtract_months(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 - months
    return date(total // 12, total % 12 + 1, 1)


def resolve_start_date(
    mode: str,
    requested: date | None,
    end_date: date,
    config: TradeIndicatorsConfig,
) -> date:
    if requested is not None:
        return requested
    if mode == "incremental":
        return subtract_months(end_date, 4)
    start_period = min(config.customs.start_period, config.comtrade.start_period)
    return date(int(start_period[:4]), int(start_period[4:6]), 1)


def collect_sources(
    config: TradeIndicatorsConfig,
    start_date: date,
    end_date: date,
    source: str = "all",
) -> None:
    if source not in {"all", "customs", "un_comtrade"}:
        raise ValueError(f"Unsupported trade source: {source}")
    chunks = periods_by_year(month_periods(start_date, end_date))
    if source in {"all", "customs"}:
        _collect_customs(config, chunks)
    if source in {"all", "un_comtrade"}:
        _collect_comtrade(config, chunks)


def _collect_customs(config: TradeIndicatorsConfig, chunks: Sequence[Sequence[str]]) -> None:
    with CustomsClient() as client:
        for chunk in chunks:
            for hs_code in config.customs.hs_codes.values():
                path, count = collect_customs_trade(
                    client,
                    hs_code,
                    chunk[0],
                    chunk[-1],
                )
                print(
                    f"source=customs hs_code={hs_code} periods={chunk[0]}:{chunk[-1]} "
                    f"rows={count} path={path}"
                )


def _collect_comtrade(config: TradeIndicatorsConfig, chunks: Sequence[Sequence[str]]) -> None:
    comtrade = config.comtrade
    with ComtradeClient() as client:
        for chunk in chunks:
            for reporter in comtrade.reporters.values():
                path, count = collect_comtrade_monthly(
                    client,
                    chunk,
                    reporter.code,
                    comtrade.partner_code,
                    list(comtrade.hs_codes.values()),
                    comtrade.flow_codes,
                    comtrade.max_records,
                )
                print(
                    f"source=un_comtrade reporter={reporter.code} "
                    f"periods={chunk[0]}:{chunk[-1]} rows={count} path={path}"
                )


def load_documents(
    roots: Sequence[Path] = BRONZE_ROOTS,
) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for root in roots:
        for path in sorted(root.glob("*/*.json")):
            with path.open(encoding="utf-8") as handle:
                payload: object = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError(f"Trade Bronze document must be an object: {path}")
            documents.append(cast(dict[str, object], payload))
    if not documents:
        raise ValueError("No Customs or UN Comtrade Bronze documents were found")
    return documents


def print_quality(report: TradeFlowQualityReport) -> None:
    print(f"input_row_count={report.input_row_count}")
    print(f"invalid_row_count={report.invalid_row_count}")
    print(f"duplicate_removed_count={report.duplicate_removed_count}")
    print(f"output_row_count={report.output_row_count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and normalize semiconductor trade-cycle inputs."
    )
    parser.add_argument("--mode", choices=("historical", "incremental"), default="incremental")
    parser.add_argument(
        "--source",
        choices=("all", "customs", "un_comtrade"),
        default="all",
        help="Collect all sources or one source before rebuilding canonical outputs.",
    )
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--skip-collect", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_trade_indicators()
    end_date = args.end_date or datetime.now(KST).date()
    start_date = resolve_start_date(args.mode, args.start_date, end_date, config)
    if not args.skip_collect:
        collect_sources(config, start_date, end_date, args.source)

    trade_flows, report = normalize_trade_documents(load_documents())
    features = derive_trade_cycle_features(trade_flows)
    silver_path = write_parquet_atomic(trade_flows, SILVER_PATH)
    feature_path = write_parquet_atomic(features, FEATURE_PATH)
    print_quality(report)
    print(f"feature_row_count={features.height}")
    print(f"silver_schema={trade_flows.schema}")
    print(f"silver_path={silver_path}")
    print(f"feature_path={feature_path}")


if __name__ == "__main__":
    main()
