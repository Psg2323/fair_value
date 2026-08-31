from fair_value.coursework.minute_price_event import (
    event_from_kis_minute_record,
    select_latest_minute_events,
)


def document() -> dict[str, object]:
    return {
        "source": "kis",
        "ticker": "005930",
        "records": [
            {
                "stck_bsop_date": "20260828",
                "stck_cntg_hour": "090000",
                "stck_prpr": "100000",
                "cntg_vol": "10",
            },
            {
                "stck_bsop_date": "20260828",
                "stck_cntg_hour": "090100",
                "stck_prpr": "100100",
                "cntg_vol": "20",
            },
        ],
    }


def test_maps_kis_minute_raw_fields() -> None:
    source = document()
    records = source["records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)

    event = event_from_kis_minute_record(source, record)

    assert event.message_key == "005930:20260828:090000"
    assert event.to_dict() == {
        "ticker": "005930",
        "trading_date": "20260828",
        "trading_time": "090000",
        "price": "100000",
        "volume": "10",
        "source": "kis",
    }


def test_selects_latest_minute_event() -> None:
    events = select_latest_minute_events([document()], limit=1)

    assert len(events) == 1
    assert events[0].trading_time == "090100"


def test_deduplicates_recollected_bronze_events() -> None:
    events = select_latest_minute_events([document(), document()])

    assert len(events) == 2
