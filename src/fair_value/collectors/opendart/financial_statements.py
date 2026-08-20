import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fair_value.collectors.opendart.client import (
    OpenDartAPIError,
    OpenDartClient,
)
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


logger = logging.getLogger(__name__)

ANNUAL_REPORT_CODE = "11011"
CONSOLIDATED_FINANCIAL_STATEMENTS = "CFS"


def fetch_financial_statement(
    client: OpenDartClient,
    corp_code: str,
    business_year: int,
    report_code: str = ANNUAL_REPORT_CODE,
    fs_div: str = CONSOLIDATED_FINANCIAL_STATEMENTS,
) -> dict[str, object] | None:
    """단일회사의 전체 재무제표를 조회합니다."""
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
                "%s년 %s 재무제표가 없습니다.",
                business_year,
                corp_code,
            )
            return None

        raise


def collect_annual_financial_statements(
    client: OpenDartClient,
    ticker: str,
    corp_code: str,
    start_year: int = 2015,
    end_year: int = 2025,
    storage: LocalStorage | None = None,
    request_delay: float = 0.2,
) -> list[tuple[int, Path, int]]:
    """연결 사업보고서 재무제표를 연도별 Bronze JSON으로 저장합니다."""
    if start_year > end_year:
        raise ValueError("시작 연도는 종료 연도보다 늦을 수 없습니다.")

    target_storage = storage or LocalStorage()
    results: list[tuple[int, Path, int]] = []

    for business_year in range(start_year, end_year + 1):
        payload = fetch_financial_statement(
            client=client,
            corp_code=corp_code,
            business_year=business_year,
        )

        if payload is None:
            continue

        records = payload.get("list")
        record_count = len(records) if isinstance(records, list) else 0

        document = {
            "source": "opendart",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "request": {
                "ticker": ticker,
                "corp_code": corp_code,
                "business_year": business_year,
                "report_code": ANNUAL_REPORT_CODE,
                "fs_div": CONSOLIDATED_FINANCIAL_STATEMENTS,
            },
            "record_count": record_count,
            "response": payload,
        }

        relative_path = (
            f"opendart/financial_statements/{ticker}/"
            f"{business_year}_11011_CFS.json"
        )

        saved_path = target_storage.write_json(
            layer=DataLayer.BRONZE,
            relative_path=relative_path,
            data=document,
        )

        results.append((business_year, saved_path, record_count))

        logger.info(
            "%s %d년 재무제표 저장: %d개 계정",
            ticker,
            business_year,
            record_count,
        )

        time.sleep(request_delay)

    return results