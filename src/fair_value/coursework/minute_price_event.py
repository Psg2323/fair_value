from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class MinutePriceRawEvent:
    """Kafka event projected directly from one KIS minute-price Bronze row."""

    ticker: str
    trading_date: str
    trading_time: str
    price: str
    volume: str
    source: str

    @property
    def message_key(self) -> str:
        return f"{self.ticker}:{self.trading_date}:{self.trading_time}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "trading_date": self.trading_date,
            "trading_time": self.trading_time,
            "price": self.price,
            "volume": self.volume,
            "source": self.source,
        }


def event_from_kis_minute_record(
    document: Mapping[str, object],
    record: Mapping[str, object],
) -> MinutePriceRawEvent:
    return MinutePriceRawEvent(
        ticker=_required_str(document, "ticker"),
        trading_date=_required_str(record, "stck_bsop_date"),
        trading_time=_required_str(record, "stck_cntg_hour"),
        price=_required_str(record, "stck_prpr"),
        volume=_required_str(record, "cntg_vol"),
        source=_required_str(document, "source"),
    )


def events_from_kis_minute_document(
    document: Mapping[str, object],
) -> list[MinutePriceRawEvent]:
    raw_records = document.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("KIS minute Bronze field 'records' must be a list")
    return [
        event_from_kis_minute_record(document, cast(Mapping[str, object], row))
        for row in raw_records
        if isinstance(row, Mapping)
    ]


def select_latest_minute_events(
    documents: Iterable[Mapping[str, object]],
    limit: int | None = None,
) -> list[MinutePriceRawEvent]:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")
    raw_events = [
        event for document in documents for event in events_from_kis_minute_document(document)
    ]
    events_by_key: dict[str, MinutePriceRawEvent] = {}
    for event in raw_events:
        events_by_key[event.message_key] = event
    events = list(events_by_key.values())
    events.sort(key=lambda event: (event.trading_date, event.trading_time, event.ticker))
    return events[-limit:] if limit is not None else events


def _required_str(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"KIS minute Bronze field '{key}' must be a non-empty string")
    return value
