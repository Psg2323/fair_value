import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from confluent_kafka import KafkaError, Message, Producer

from fair_value.coursework.market_price_event import (
    MarketPriceRawEvent,
    select_latest_events,
)

DEFAULT_TOPIC = "fair_value.market_price.raw.v1"
DEFAULT_BRONZE_ROOT = Path("data/bronze/kis/daily_prices")


def load_kis_documents(bronze_root: Path) -> list[dict[str, object]]:
    """Load KIS Bronze documents from the existing ticker directory layout."""
    paths = sorted(bronze_root.glob("*/*.json"))

    if not paths:
        raise FileNotFoundError(f"No KIS Bronze JSON files found under {bronze_root}")

    documents: list[dict[str, object]] = []

    for path in paths:
        with path.open(encoding="utf-8") as handle:
            raw_document: object = json.load(handle)

        if not isinstance(raw_document, dict):
            raise ValueError(f"KIS Bronze document must be an object: {path}")

        documents.append(cast(dict[str, object], raw_document))

    return documents


def produce_events(
    events: Sequence[MarketPriceRawEvent],
    bootstrap_servers: str,
    topic: str,
    timeout_seconds: float,
) -> int:
    """Publish events and return the broker-acknowledged delivery count."""
    producer = Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "fair-value-course-producer",
        }
    )
    delivered_count = 0
    failures: list[str] = []

    def on_delivery(error: KafkaError | None, _message: Message) -> None:
        nonlocal delivered_count

        if error is not None:
            failures.append(str(error))
            return

        delivered_count += 1

    for event in events:
        payload = json.dumps(
            event.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()

        while True:
            try:
                producer.produce(
                    topic=topic,
                    key=event.message_key.encode(),
                    value=payload,
                    on_delivery=on_delivery,
                )
                break
            except BufferError:
                producer.poll(0.1)

        producer.poll(0)

    remaining = producer.flush(timeout_seconds)

    if remaining:
        raise RuntimeError(f"Kafka producer flush timed out with {remaining} messages pending")

    if failures:
        raise RuntimeError(f"Kafka delivery failed: {failures[0]}")

    return delivered_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay KIS Bronze prices to Kafka")
    parser.add_argument("--bootstrap-servers", default="localhost:29092")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--bronze-root", type=Path, default=DEFAULT_BRONZE_ROOT)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    documents = load_kis_documents(args.bronze_root)
    events = select_latest_events(documents, limit=args.limit)
    sent_count = produce_events(
        events=events,
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        timeout_seconds=args.timeout_seconds,
    )

    print(f"topic={args.topic}")
    print(f"requested_count={len(events)}")
    print(f"sent_count={sent_count}")

    if sent_count != len(events):
        raise RuntimeError(f"Kafka acknowledged {sent_count} of {len(events)} requested messages")


if __name__ == "__main__":
    main()
