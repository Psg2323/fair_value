import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from fair_value.collectors.kis.client import KISAPIError, KISClient
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


logger = logging.getLogger(__name__)

DAILY_PRICE_PATH = (
    "/uapi/domestic-stock/v1/quotations/"
    "inquire-daily-itemchartprice"
)
DAILY_PRICE_TR_ID = "FHKST03010100"


def fetch_daily_prices_page(
    client: KISClient,
    ticker: str,
    start_date: date,
    end_date: date,
    adjusted: bool = True,
) -> list[dict[str, object]]:
    """국내주식 일봉을 최대 100건 조회합니다."""
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
        "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "1" if adjusted else "0",
    }

    payload = client.get(
        path=DAILY_PRICE_PATH,
        tr_id=DAILY_PRICE_TR_ID,
        params=params,
    )

    output = payload.get("output2")

    if not isinstance(output, list):
        raise KISAPIError("KIS 일봉 응답에 output2 목록이 없습니다.")

    return [
        cast(dict[str, object], row)
        for row in output
        if isinstance(row, dict)
    ]


def fetch_daily_prices(
    client: KISClient,
    ticker: str,
    start_date: date,
    end_date: date,
    adjusted: bool = True,
    request_delay: float = 0.6,
) -> list[dict[str, object]]:
    """날짜를 역순으로 이동하며 전체 일봉을 수집합니다."""
    if start_date > end_date:
        raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")

    records_by_date: dict[str, dict[str, object]] = {}
    current_end = end_date

    while current_end >= start_date:
        page = _fetch_page_with_retry(
            client=client,
            ticker=ticker,
            start_date=start_date,
            end_date=current_end,
            adjusted=adjusted,
        )

        if not page:
            break

        page_dates: list[date] = []

        for row in page:
            date_text = row.get("stck_bsop_date")

            if not isinstance(date_text, str):
                continue

            try:
                business_date = datetime.strptime(
                    date_text,
                    "%Y%m%d",
                ).date()
            except ValueError:
                continue

            page_dates.append(business_date)

            if start_date <= business_date <= end_date:
                records_by_date[date_text] = row

        if not page_dates:
            break

        oldest_date = min(page_dates)

        logger.info(
            "%s 수집: %s까지, 누적 %d건",
            ticker,
            oldest_date.isoformat(),
            len(records_by_date),
        )

        if oldest_date <= start_date:
            break

        next_end = oldest_date - timedelta(days=1)

        if next_end >= current_end:
            raise RuntimeError("KIS 페이지 날짜가 이전으로 이동하지 않습니다.")

        current_end = next_end
        time.sleep(request_delay)

    return [
        records_by_date[date_text]
        for date_text in sorted(records_by_date)
    ]


def _fetch_page_with_retry(
    client: KISClient,
    ticker: str,
    start_date: date,
    end_date: date,
    adjusted: bool,
    max_attempts: int = 3,
) -> list[dict[str, object]]:
    """호출 제한 오류가 발생하면 대기 후 재시도합니다."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fetch_daily_prices_page(
                client=client,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                adjusted=adjusted,
            )
        except KISAPIError as error:
            is_rate_limit = "EGW00201" in str(error)

            if not is_rate_limit or attempt == max_attempts:
                raise

            logger.warning(
                "KIS 호출 제한 발생: 61초 후 재시도 (%d/%d)",
                attempt,
                max_attempts,
            )
            time.sleep(61)

    raise RuntimeError("KIS 일봉 재시도 처리가 비정상 종료됐습니다.")


def collect_daily_prices(
    client: KISClient,
    ticker: str,
    start_date: date,
    end_date: date,
    storage: LocalStorage | None = None,
) -> tuple[Path, list[dict[str, object]]]:
    """일봉을 수집하여 Bronze JSON으로 저장합니다."""
    target_storage = storage or LocalStorage()

    records = fetch_daily_prices(
        client=client,
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        adjusted=True,
    )

    document = {
        "source": "kis",
        "ticker": ticker,
        "adjusted": True,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records,
    }

    relative_path = (
        f"kis/daily_prices/{ticker}/"
        f"{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )

    saved_path = target_storage.write_json(
        layer=DataLayer.BRONZE,
        relative_path=relative_path,
        data=document,
    )

    return saved_path, records