import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.opendart.client import (
    OpenDartAPIError,
    OpenDartClient,
)
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer

logger = logging.getLogger(__name__)

ANNUAL_REPORT_CODE = "11011"
REPORT_CODES = {
    "11013": "q1",
    "11012": "half",
    "11014": "q3",
    "11011": "annual",
}
CONSOLIDATED_FINANCIAL_STATEMENTS = "CFS"


def fetch_financial_statement(
    client: OpenDartClient,
    corp_code: str,
    business_year: int,
    report_code: str = ANNUAL_REPORT_CODE,
    fs_div: str = CONSOLIDATED_FINANCIAL_STATEMENTS,
) -> dict[str, object] | None:
    """Fetch one company's complete financial statement report."""
    try:
        return client.get_json(
            path="/api/fnlttSinglAcntAll.json",
            params={
                "corp_code": corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
                "fs_div": fs_div,
            },
        )
    except OpenDartAPIError as error:
        if error.code == "013":
            logger.warning(
                "No OpenDART statement: corp=%s year=%d report=%s",
                corp_code,
                business_year,
                report_code,
            )
            return None

        raise


def collect_financial_statements(
    client: OpenDartClient,
    ticker: str,
    corp_code: str,
    start_year: int,
    end_year: int,
    report_codes: Sequence[str] = tuple(REPORT_CODES),
    storage: LocalStorage | None = None,
    request_delay: float = 0.2,
) -> list[tuple[int, str, Path, int]]:
    """Store requested consolidated financial statements as Bronze JSON."""
    if start_year > end_year:
        raise ValueError("start_year must not be later than end_year")

    unknown_codes = set(report_codes) - set(REPORT_CODES)
    if unknown_codes:
        raise ValueError(f"Unknown OpenDART report codes: {sorted(unknown_codes)}")

    target_storage = storage or LocalStorage()
    results: list[tuple[int, str, Path, int]] = []

    for business_year in range(start_year, end_year + 1):
        for report_code in report_codes:
            payload = fetch_financial_statement(
                client=client,
                corp_code=corp_code,
                business_year=business_year,
                report_code=report_code,
            )

            if payload is None:
                time.sleep(request_delay)
                continue

            records = payload.get("list")
            record_count = len(records) if isinstance(records, list) else 0
            document = {
                "source": "opendart",
                "collected_at": datetime.now(UTC).isoformat(),
                "request": {
                    "ticker": ticker,
                    "corp_code": corp_code,
                    "business_year": business_year,
                    "report_code": report_code,
                    "report_period": REPORT_CODES[report_code],
                    "fs_div": CONSOLIDATED_FINANCIAL_STATEMENTS,
                },
                "record_count": record_count,
                "response": payload,
            }
            relative_path = (
                f"opendart/financial_statements/{ticker}/{business_year}_{report_code}_CFS.json"
            )
            saved_path = target_storage.write_json(
                layer=DataLayer.BRONZE,
                relative_path=relative_path,
                data=document,
            )
            results.append((business_year, report_code, saved_path, record_count))
            logger.info(
                "Stored OpenDART statement: ticker=%s year=%d report=%s rows=%d",
                ticker,
                business_year,
                report_code,
                record_count,
            )
            time.sleep(request_delay)

    return results


def collect_annual_financial_statements(
    client: OpenDartClient,
    ticker: str,
    corp_code: str,
    start_year: int = 2015,
    end_year: int = 2025,
    storage: LocalStorage | None = None,
    request_delay: float = 0.2,
) -> list[tuple[int, Path, int]]:
    """Backward-compatible annual-report collector."""
    results = collect_financial_statements(
        client=client,
        ticker=ticker,
        corp_code=corp_code,
        start_year=start_year,
        end_year=end_year,
        report_codes=(ANNUAL_REPORT_CODE,),
        storage=storage,
        request_delay=request_delay,
    )
    return [
        (business_year, saved_path, record_count)
        for business_year, _, saved_path, record_count in results
    ]
