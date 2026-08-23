import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.opendart.client import (
    OpenDartAPIError,
    OpenDartClient,
)
from fair_value.collectors.opendart.financial_statements import REPORT_CODES
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer

logger = logging.getLogger(__name__)

PERIODIC_REPORT_ENDPOINTS = {
    "share_counts": "/api/stockTotqySttus.json",
    "dividends": "/api/alotMatter.json",
}


def fetch_periodic_report(
    client: OpenDartClient,
    endpoint: str,
    corp_code: str,
    business_year: int,
    report_code: str,
) -> dict[str, object] | None:
    """Fetch one structured section from a periodic report."""
    if endpoint not in PERIODIC_REPORT_ENDPOINTS:
        raise ValueError(f"Unknown OpenDART periodic endpoint: {endpoint}")

    try:
        return client.get_json(
            path=PERIODIC_REPORT_ENDPOINTS[endpoint],
            params={
                "corp_code": corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
            },
        )
    except OpenDartAPIError as error:
        if error.code == "013":
            logger.warning(
                "No OpenDART %s data: corp=%s year=%d report=%s",
                endpoint,
                corp_code,
                business_year,
                report_code,
            )
            return None

        raise


def collect_periodic_reports(
    client: OpenDartClient,
    endpoint: str,
    ticker: str,
    corp_code: str,
    start_year: int,
    end_year: int,
    report_codes: Sequence[str] = tuple(REPORT_CODES),
    storage: LocalStorage | None = None,
    request_delay: float = 0.2,
) -> list[tuple[int, str, Path, int]]:
    """Collect a structured periodic-report section into Bronze."""
    if start_year > end_year:
        raise ValueError("start_year must not be later than end_year")
    if endpoint not in PERIODIC_REPORT_ENDPOINTS:
        raise ValueError(f"Unknown OpenDART periodic endpoint: {endpoint}")

    unknown_codes = set(report_codes) - set(REPORT_CODES)
    if unknown_codes:
        raise ValueError(f"Unknown OpenDART report codes: {sorted(unknown_codes)}")

    target_storage = storage or LocalStorage()
    results: list[tuple[int, str, Path, int]] = []

    for business_year in range(start_year, end_year + 1):
        for report_code in report_codes:
            payload = fetch_periodic_report(
                client=client,
                endpoint=endpoint,
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
                },
                "record_count": record_count,
                "response": payload,
            }
            relative_path = f"opendart/{endpoint}/{ticker}/{business_year}_{report_code}.json"
            saved_path = target_storage.write_json(
                layer=DataLayer.BRONZE,
                relative_path=relative_path,
                data=document,
            )
            results.append((business_year, report_code, saved_path, record_count))
            time.sleep(request_delay)

    return results
