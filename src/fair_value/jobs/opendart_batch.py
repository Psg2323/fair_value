from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fair_value.collectors.opendart.client import OpenDartClient
from fair_value.collectors.opendart.disclosures import collect_periodic_disclosures
from fair_value.collectors.opendart.financial_statements import (
    REPORT_CODES,
    collect_financial_statements,
)
from fair_value.collectors.opendart.periodic_reports import (
    collect_periodic_reports,
)
from fair_value.config_loader import load_companies


def run_opendart_batch(
    start_year: int,
    end_year: int,
    as_of_date: date,
    request_delay: float,
) -> None:
    companies = load_companies()

    with OpenDartClient() as client:
        for company in companies.companies.values():
            if not company.enabled:
                continue

            statements = collect_financial_statements(
                client=client,
                ticker=company.ticker,
                corp_code=company.opendart_corp_code,
                start_year=start_year,
                end_year=end_year,
                report_codes=tuple(REPORT_CODES),
                request_delay=request_delay,
            )
            share_counts = collect_periodic_reports(
                client=client,
                endpoint="share_counts",
                ticker=company.ticker,
                corp_code=company.opendart_corp_code,
                start_year=start_year,
                end_year=end_year,
                report_codes=tuple(REPORT_CODES),
                request_delay=request_delay,
            )
            dividends = collect_periodic_reports(
                client=client,
                endpoint="dividends",
                ticker=company.ticker,
                corp_code=company.opendart_corp_code,
                start_year=start_year,
                end_year=end_year,
                report_codes=tuple(REPORT_CODES),
                request_delay=request_delay,
            )
            _, disclosure_count = collect_periodic_disclosures(
                client=client,
                ticker=company.ticker,
                corp_code=company.opendart_corp_code,
                begin_date=date(start_year, 1, 1),
                end_date=as_of_date,
            )
            print(
                f"ticker={company.ticker} statements={len(statements)} "
                f"share_reports={len(share_counts)} dividend_reports={len(dividends)} "
                f"disclosures={disclosure_count}"
            )


def resolve_year_range(
    mode: str,
    requested_start_year: int | None,
    requested_end_year: int | None,
    current_year: int,
) -> tuple[int, int]:
    """Limit routine refreshes while preserving an explicit historical mode."""
    end_year = requested_end_year or current_year
    if requested_start_year is not None:
        start_year = requested_start_year
    elif mode == "historical":
        start_year = 2015
    else:
        start_year = max(2015, end_year - 1)
    if start_year > end_year:
        raise ValueError("start_year must not be later than end_year")
    return start_year, end_year


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect OpenDART point-in-time financial raw inputs."
    )
    parser.add_argument("--mode", choices=("historical", "incremental"), default="incremental")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--as-of-date", type=date.fromisoformat)
    parser.add_argument("--request-delay", type=float, default=0.2)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    start_year, end_year = resolve_year_range(
        args.mode,
        args.start_year,
        args.end_year,
        today.year,
    )
    as_of_date = args.as_of_date or today

    run_opendart_batch(
        start_year=start_year,
        end_year=end_year,
        as_of_date=as_of_date,
        request_delay=args.request_delay,
    )


if __name__ == "__main__":
    main()
