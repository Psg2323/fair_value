from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from fair_value.jobs.market_price_batch import resolve_incremental_end_date

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
