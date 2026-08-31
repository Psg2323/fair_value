from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.customs.client import CustomsClient
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def collect_customs_trade(
    client: CustomsClient,
    hs_code: str,
    start_period: str,
    end_period: str,
    storage: LocalStorage | None = None,
) -> tuple[Path, int]:
    """Collect one HS series and persist the unmodified response rows to Bronze."""
    rows = client.get_item_trade(hs_code, start_period, end_period)
    collected_at = datetime.now(UTC)
    document = {
        "source": "customs",
        "collected_at": collected_at.isoformat(),
        "request": {
            "hs_code": hs_code,
            "start_period": start_period,
            "end_period": end_period,
        },
        "response": {"rows": rows},
    }
    target_storage = storage or LocalStorage()
    path = target_storage.write_json(
        DataLayer.BRONZE,
        (
            f"customs/item_trade/{hs_code}/{start_period}_{end_period}_"
            f"{collected_at:%Y%m%dT%H%M%SZ}.json"
        ),
        document,
    )
    return path, len(rows)
