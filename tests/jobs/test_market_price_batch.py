from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from fair_value.jobs.market_price_batch import (
    collect_incremental_prices,
    resolve_incremental_end_date,
)

KST = ZoneInfo("Asia/Seoul")


def test_incremental_end_date_excludes_current_day_before_ready_time() -> None:
    now = datetime(2026, 8, 24, 16, 9, tzinfo=KST)

    assert resolve_incremental_end_date(None, now) == date(2026, 8, 23)


def test_incremental_end_date_includes_current_day_at_ready_time() -> None:
    now = datetime(2026, 8, 24, 16, 10, tzinfo=KST)

    assert resolve_incremental_end_date(None, now) == date(2026, 8, 24)


def test_incremental_end_date_preserves_explicit_backfill_date() -> None:
    requested = date(2026, 8, 20)
    now = datetime(2026, 8, 24, 9, 0, tzinfo=KST)

    assert resolve_incremental_end_date(requested, now) == requested


def test_incremental_end_date_requires_timezone_aware_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_incremental_end_date(None, datetime(2026, 8, 24, 16, 20))


def test_new_ticker_uses_bootstrap_start_date(monkeypatch: pytest.MonkeyPatch) -> None:
    import polars as pl

    class Company:
        enabled = True
        ticker = "000990"

    class Companies:
        companies = {"db_hitek": Company()}

    class Client:
        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    calls: list[tuple[str, date, date]] = []

    def collect(*, ticker: str, start_date: date, end_date: date, **_: object) -> tuple[str, list]:
        calls.append((ticker, start_date, end_date))
        return "unused", []

    monkeypatch.setattr("fair_value.jobs.market_price_batch.load_companies", lambda: Companies())
    monkeypatch.setattr("fair_value.jobs.market_price_batch.KISClient", Client)
    monkeypatch.setattr("fair_value.jobs.market_price_batch.collect_daily_prices", collect)
    frame = pl.DataFrame({"ticker": ["005930"], "trading_date": [date(2026, 8, 28)]})

    collect_incremental_prices(frame, date(2026, 8, 31), date(2020, 1, 1))
