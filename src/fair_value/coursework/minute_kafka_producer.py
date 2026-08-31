import argparse
from pathlib import Path

from fair_value.coursework.kafka_producer import (
    load_kis_documents,
    produce_events,
)
from fair_value.coursework.minute_price_event import select_latest_minute_events

DEFAULT_TOPIC = "fair_value.market_price.minute.raw.v1"
DEFAULT_BRONZE_ROOT = Path("data/bronze/kis/minute_prices")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay KIS minute Bronze data to Kafka")
    parser.add_argument("--bootstrap-servers", default="localhost:29092")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--bronze-root", type=Path, default=DEFAULT_BRONZE_ROOT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--trading-date", help="Only publish yyyyMMdd events.")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.repeat <= 0:
        raise ValueError("repeat must be greater than zero")
    documents = load_kis_documents(args.bronze_root)
    unique_events = select_latest_minute_events(documents, args.limit)
    if args.trading_date:
        unique_events = [
            event for event in unique_events if event.trading_date == args.trading_date
        ]
    events = unique_events * args.repeat

    sent_count = produce_events(
        events,
        args.bootstrap_servers,
        args.topic,
        args.timeout_seconds,
    )
    print(f"topic={args.topic}")
    print(f"unique_event_count={len(unique_events)}")
    print(f"replay_factor={args.repeat}")
    print(f"requested_count={len(events)}")
    print(f"sent_count={sent_count}")
    if sent_count != len(events):
        raise RuntimeError(f"Kafka acknowledged {sent_count} of {len(events)} messages")


if __name__ == "__main__":
    main()
