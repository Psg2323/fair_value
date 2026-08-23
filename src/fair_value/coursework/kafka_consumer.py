import argparse
import json
import time
from uuid import uuid4

from confluent_kafka import Consumer, KafkaException

DEFAULT_TOPIC = "fair_value.market_price.raw.v1"
EXPECTED_FIELDS = {
    "ticker",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "adjusted",
}


def consume_events(
    bootstrap_servers: str,
    topic: str,
    expected_count: int,
    timeout_seconds: float,
    group_id: str | None = None,
) -> int:
    """Consume and validate the expected number of raw market-price events."""
    if expected_count <= 0:
        raise ValueError("expected_count must be greater than zero")

    resolved_group_id = group_id or f"fair-value-course-{uuid4()}"
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": resolved_group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    received_count = 0
    deadline = time.monotonic() + timeout_seconds
    consumer.subscribe([topic])

    try:
        while received_count < expected_count and time.monotonic() < deadline:
            message = consumer.poll(0.5)

            if message is None:
                continue

            if message.error() is not None:
                raise KafkaException(message.error())

            raw_payload = message.value()

            if raw_payload is None:
                raise ValueError("Kafka message value must not be null")

            payload: object = json.loads(raw_payload)

            if not isinstance(payload, dict):
                raise ValueError("Kafka message value must be a JSON object")

            missing_fields = EXPECTED_FIELDS.difference(payload)

            if missing_fields:
                missing_text = ", ".join(sorted(missing_fields))
                raise ValueError(f"Kafka message is missing fields: {missing_text}")

            received_count += 1
    finally:
        consumer.close()

    if received_count != expected_count:
        raise TimeoutError(
            f"Consumer received {received_count} of {expected_count} messages "
            f"within {timeout_seconds:.1f}s"
        )

    return received_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume KIS raw price events from Kafka")
    parser.add_argument("--bootstrap-servers", default="localhost:29092")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--expected-count", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--group-id")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    received_count = consume_events(
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        expected_count=args.expected_count,
        timeout_seconds=args.timeout_seconds,
        group_id=args.group_id,
    )

    print(f"topic={args.topic}")
    print(f"received_count={received_count}")


if __name__ == "__main__":
    main()
