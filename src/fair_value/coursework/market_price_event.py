from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class MarketPriceRawEvent:
    """Minimal Kafka event projected from one KIS Bronze price record."""

    ticker: str
    trading_date: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    source: str
    adjusted: bool

    @property
    def message_key(self) -> str:
        return f"{self.ticker}:{self.trading_date}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ticker": self.ticker,
            "trading_date": self.trading_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
            "adjusted": self.adjusted,
        }


def event_from_kis_record(
    document: Mapping[str, object],
    record: Mapping[str, object],
) -> MarketPriceRawEvent:
    """Map existing KIS Bronze fields without normalizing raw values."""
    return MarketPriceRawEvent(
        ticker=_required_str(document, "ticker"),
        trading_date=_required_str(record, "stck_bsop_date"),
        open=_required_str(record, "stck_oprc"),
        high=_required_str(record, "stck_hgpr"),
        low=_required_str(record, "stck_lwpr"),
        close=_required_str(record, "stck_clpr"),
        volume=_required_str(record, "acml_vol"),
        source=_required_str(document, "source"),
        adjusted=_required_bool(document, "adjusted"),
    )


def events_from_kis_document(
    document: Mapping[str, object],
) -> list[MarketPriceRawEvent]:
    """Project every record from one KIS Bronze document."""
    raw_records = document.get("records")

    if not isinstance(raw_records, list):
        raise ValueError("KIS Bronze field 'records' must be a list")

    events: list[MarketPriceRawEvent] = []

    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise ValueError(f"KIS Bronze record at index {index} must be an object")

        record = cast(Mapping[str, object], raw_record)
        events.append(event_from_kis_record(document, record))

    return events


def select_latest_events(
    documents: Iterable[Mapping[str, object]],
    limit: int | None = None,
) -> list[MarketPriceRawEvent]:
    """Return deterministic latest events across documents, ordered by date and ticker."""
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    events = [event for document in documents for event in events_from_kis_document(document)]
    events.sort(key=lambda event: (event.trading_date, event.ticker))

    if limit is not None:
        events = events[-limit:]

    return events


def _required_str(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)

    if not isinstance(value, str) or not value:
        raise ValueError(f"KIS Bronze field '{key}' must be a non-empty string")

    return value


def _required_bool(mapping: Mapping[str, object], key: str) -> bool:
    value = mapping.get(key)

    if not isinstance(value, bool):
        raise ValueError(f"KIS Bronze field '{key}' must be a boolean")

    return value
