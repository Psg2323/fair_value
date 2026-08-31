import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

from fair_value.collectors.kis.client import KISAPIError, KISClient
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer

logger = logging.getLogger(__name__)

MINUTE_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
MINUTE_PRICE_TR_ID = "FHKST03010230"
MARKET_OPEN = "090000"
MARKET_CLOSE = "153000"


def fetch_minute_prices_page(
    client: KISClient,
    ticker: str,
    trading_date: date,
    end_time: str,
) -> list[dict[str, object]]:
    """Fetch up to 120 KRX minute observations ending at end_time."""
    if len(end_time) != 6 or not end_time.isdigit():
        raise ValueError("end_time must be HHMMSS")
    payload = client.get(
        path=MINUTE_PRICE_PATH,
        tr_id=MINUTE_PRICE_TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_HOUR_1": end_time,
            "FID_INPUT_DATE_1": trading_date.strftime("%Y%m%d"),
            "FID_PW_DATA_INCU_YN": "Y",
            "FID_FAKE_TICK_INCU_YN": "",
        },
    )
    output = payload.get("output2")
    if not isinstance(output, list):
        raise KISAPIError("KIS minute-price response has no output2 list")
    return [cast(dict[str, object], row) for row in output if isinstance(row, dict)]


def fetch_minute_prices(
    client: KISClient,
    ticker: str,
    trading_date: date,
    request_delay: float = 0.2,
    max_pages: int = 10,
) -> list[dict[str, object]]:
    """Page backward through one KRX session and deduplicate timestamp rows."""
    expected_date = trading_date.strftime("%Y%m%d")
    current_end = MARKET_CLOSE
    records: dict[str, dict[str, object]] = {}

    for _ in range(max_pages):
        page = _fetch_page_with_retry(client, ticker, trading_date, current_end)
        if not page:
            break
        page_times: list[str] = []
        for row in page:
            row_date = row.get("stck_bsop_date")
            row_time = row.get("stck_cntg_hour")
            valid_time = isinstance(row_time, str) and len(row_time) == 6
            if row_date == expected_date and valid_time:
                records[cast(str, row_time)] = row
                page_times.append(cast(str, row_time))
        if not page_times:
            break
        oldest = min(page_times)
        logger.info(
            "%s %s minute collection: through %s, cumulative %d rows",
            ticker,
            trading_date,
            oldest,
            len(records),
        )
        if oldest <= MARKET_OPEN or len(page) < 120:
            break
        next_end = (datetime.strptime(oldest, "%H%M%S") - timedelta(seconds=1)).strftime("%H%M%S")
        if next_end >= current_end:
            raise RuntimeError("KIS minute-page cursor did not move backward")
        current_end = next_end
        time.sleep(request_delay)

    return [records[key] for key in sorted(records)]


def _fetch_page_with_retry(
    client: KISClient,
    ticker: str,
    trading_date: date,
    end_time: str,
    max_attempts: int = 3,
) -> list[dict[str, object]]:
    for attempt in range(1, max_attempts + 1):
        try:
            return fetch_minute_prices_page(client, ticker, trading_date, end_time)
        except KISAPIError as error:
            if "EGW00201" not in str(error) or attempt == max_attempts:
                raise
            logger.warning(
                "KIS rate limit: retrying minute page after 61 seconds (%d/%d)",
                attempt,
                max_attempts,
            )
            time.sleep(61)
    raise RuntimeError("KIS minute-price retry ended unexpectedly")


def collect_minute_prices(
    client: KISClient,
    ticker: str,
    trading_date: date,
    storage: LocalStorage | None = None,
) -> tuple[Path, list[dict[str, object]]]:
    """Collect one ticker-session into an immutable Bronze JSON document."""
    target_storage = storage or LocalStorage()
    records = fetch_minute_prices(client, ticker, trading_date)
    collected_at = datetime.now(UTC)
    document = {
        "source": "kis",
        "dataset": "minute_prices",
        "ticker": ticker,
        "trading_date": trading_date.isoformat(),
        "collected_at": collected_at.isoformat(),
        "record_count": len(records),
        "records": records,
    }
    relative_path = (
        f"kis/minute_prices/{ticker}/{trading_date:%Y%m%d}_{collected_at:%Y%m%dT%H%M%SZ}.json"
    )
    saved_path = target_storage.write_json(
        layer=DataLayer.BRONZE,
        relative_path=relative_path,
        data=document,
    )
    return saved_path, records
