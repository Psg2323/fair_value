import json
from pathlib import Path

import pytest

from fair_value.coursework.market_price_event import (
    event_from_kis_record,
    events_from_kis_document,
    select_latest_events,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "kis_daily_prices_005930_sample.json"


def load_fixture() -> dict[str, object]:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        document: object = json.load(handle)

    assert isinstance(document, dict)
    return document


def test_maps_existing_kis_fields_without_numeric_normalization() -> None:
    document = load_fixture()
    records = document["records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)

    event = event_from_kis_record(document, record)

    assert event.message_key == "005930:20260804"
    assert event.to_dict() == {
        "ticker": "005930",
        "trading_date": "20260804",
        "open": "244500",
        "high": "244500",
        "low": "228000",
        "close": "240000",
        "volume": "29433821",
        "source": "kis",
        "adjusted": True,
    }


def test_projects_all_fixture_records() -> None:
    events = events_from_kis_document(load_fixture())

    assert len(events) == 12
    assert events[0].trading_date == "20260804"
    assert events[-1].trading_date == "20260820"


def test_selects_latest_events_deterministically() -> None:
    document = load_fixture()

    events = select_latest_events([document], limit=3)

    assert [event.trading_date for event in events] == [
        "20260818",
        "20260819",
        "20260820",
    ]


def test_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit must be greater than zero"):
        select_latest_events([load_fixture()], limit=0)


def test_rejects_missing_required_raw_field() -> None:
    document = load_fixture()
    records = document["records"]
    assert isinstance(records, list)
    record = dict(records[0])
    del record["stck_clpr"]

    with pytest.raises(ValueError, match="stck_clpr"):
        event_from_kis_record(document, record)
