import argparse
from dataclasses import dataclass

from fair_value.coursework.kafka_producer import produce_events

DEFAULT_TOPIC = "fair_value.market_price.minute.raw.v1"


@dataclass(frozen=True, slots=True)
class FaultEvent:
    index: int
    fault: str

    @property
    def message_key(self) -> str:
        return f"fault:{self.fault}:{self.index}"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ticker": "005930",
            "trading_date": "20260828",
            "trading_time": f"12{self.index % 60:02d}00",
            "price": "100000",
            "volume": "10",
            "source": "fault_injection",
        }
        if self.fault == "missing_price":
            payload.pop("price")
        elif self.fault == "bad_date":
            payload["trading_date"] = "not-a-date"
        elif self.fault == "negative_price":
            payload["price"] = "-1"
        else:
            raise ValueError(f"Unsupported fault: {self.fault}")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject safe invalid minute events")
    parser.add_argument("--bootstrap-servers", default="localhost:29092")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument(
        "--fault",
        choices=("missing_price", "bad_date", "negative_price"),
        default="missing_price",
    )
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    if args.count <= 0:
        raise ValueError("count must be greater than zero")
    events = [FaultEvent(index, args.fault) for index in range(args.count)]
    sent = produce_events(events, args.bootstrap_servers, args.topic, 30)
    print(f"topic={args.topic}")
    print(f"fault={args.fault}")
    print(f"sent_count={sent}")


if __name__ == "__main__":
    main()
