from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.ecos.client import EcosClient
from fair_value.config_loader import EcosIndicatorConfig
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def collect_ecos_indicator(
    client: EcosClient,
    indicator_id: str,
    indicator: EcosIndicatorConfig,
    start_period: str,
    end_period: str,
    storage: LocalStorage | None = None,
) -> tuple[Path, int]:
    rows = client.get_statistics(
        indicator.stat_code,
        indicator.frequency,
        start_period,
        end_period,
        indicator.item_code,
    )
    document = {
        "source": "ecos",
        "collected_at": datetime.now(UTC).isoformat(),
        "request": {
            "indicator_id": indicator_id,
            "stat_code": indicator.stat_code,
            "item_code": indicator.item_code,
            "frequency": indicator.frequency,
            "configured_unit": indicator.unit,
            "start_period": start_period,
            "end_period": end_period,
        },
        "record_count": len(rows),
        "response": {"rows": rows},
    }
    target = storage or LocalStorage()
    relative = f"ecos/statistics/{indicator_id}/{start_period}_{end_period}.json"
    return target.write_json(DataLayer.BRONZE, relative, document), len(rows)
