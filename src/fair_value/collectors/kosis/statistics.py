from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.kosis.client import KosisClient
from fair_value.config_loader import KosisIndicatorConfig
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def collect_kosis_indicator(
    client: KosisClient,
    indicator_id: str,
    indicator: KosisIndicatorConfig,
    start_period: str,
    end_period: str,
    storage: LocalStorage | None = None,
) -> tuple[Path, int]:
    rows = client.get_statistics(
        indicator.org_id,
        indicator.table_id,
        indicator.item_code,
        indicator.region_code,
        indicator.industry_code,
        indicator.frequency,
        start_period,
        end_period,
    )
    document = {
        "source": "kosis",
        "collected_at": datetime.now(UTC).isoformat(),
        "request": {
            "indicator_id": indicator_id,
            "org_id": indicator.org_id,
            "table_id": indicator.table_id,
            "item_code": indicator.item_code,
            "region_code": indicator.region_code,
            "industry_code": indicator.industry_code,
            "frequency": indicator.frequency,
            "configured_unit": indicator.unit,
            "availability_lag_days": indicator.availability_lag_days,
            "start_period": start_period,
            "end_period": end_period,
        },
        "record_count": len(rows),
        "response": {"rows": rows},
    }
    target = storage or LocalStorage()
    relative = f"kosis/statistics/{indicator_id}/{start_period}_{end_period}.json"
    return target.write_json(DataLayer.BRONZE, relative, document), len(rows)
