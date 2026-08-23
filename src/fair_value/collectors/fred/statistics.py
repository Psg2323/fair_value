from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.fred.client import FredClient
from fair_value.config_loader import FredIndicatorConfig
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def collect_fred_indicator(
    client: FredClient,
    indicator_id: str,
    indicator: FredIndicatorConfig,
    start_period: str,
    end_period: str,
    storage: LocalStorage | None = None,
) -> tuple[Path, int]:
    if indicator.vintage_mode != "initial_release":
        raise ValueError(f"Unsupported FRED vintage mode: {indicator.vintage_mode}")
    metadata = client.get_series_metadata(indicator.series_id)
    rows = client.get_initial_release_observations(
        indicator.series_id,
        start_period,
        end_period,
    )
    document = {
        "source": "fred",
        "collected_at": datetime.now(UTC).isoformat(),
        "request": {
            "indicator_id": indicator_id,
            "series_id": indicator.series_id,
            "frequency": indicator.frequency,
            "configured_unit": indicator.unit,
            "start_period": start_period,
            "end_period": end_period,
            "vintage_mode": indicator.vintage_mode,
        },
        "record_count": len(rows),
        "response": {"series": metadata, "rows": rows},
    }
    target = storage or LocalStorage()
    relative = f"fred/statistics/{indicator_id}/{start_period}_{end_period}.json"
    return target.write_json(DataLayer.BRONZE, relative, document), len(rows)
