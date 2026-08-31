import argparse

from fair_value.coursework.kafka_consumer import consume_events

DEFAULT_TOPIC = "fair_value.market_price.minute.raw.v1"
EXPECTED_FIELDS = {
    "ticker",
    "trading_date",
    "trading_time",
    "price",
    "volume",
    "source",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume KIS minute-price Kafka events")
    parser.add_argument("--bootstrap-servers", default="localhost:29092")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--group-id")
    args = parser.parse_args()
    received_count = consume_events(
        args.bootstrap_servers,
        args.topic,
        args.expected_count,
        args.timeout_seconds,
        args.group_id,
        expected_fields=EXPECTED_FIELDS,
    )
    print(f"topic={args.topic}")
    print(f"received_count={received_count}")


if __name__ == "__main__":
    main()
