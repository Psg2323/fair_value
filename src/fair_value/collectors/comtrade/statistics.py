from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fair_value.collectors.comtrade.client import ComtradeClient
from fair_value.storage.local import LocalStorage
from fair_value.storage.paths import DataLayer


def collect_comtrade_monthly(
    client: ComtradeClient,
    periods: Sequence[str],
    reporter_code: str,
    partner_code: str,
    hs_codes: Sequence[str],
    flow_codes: Sequence[str],
    max_records: int,
    storage: LocalStorage | None = None,
) -> tuple[Path, int]:
    """Collect one bounded reporter-period request and persist its raw rows."""
    rows = client.get_monthly_trade(
        periods,
        reporter_code,
        partner_code,
        hs_codes,
        flow_codes,
        max_records,
    )
    collected_at = datetime.now(UTC)
    document = {
        "source": "un_comtrade",
        "collected_at": collected_at.isoformat(),
        "request": {
            "periods": list(periods),
            "reporter_code": reporter_code,
            "partner_code": partner_code,
            "hs_codes": list(hs_codes),
            "flow_codes": list(flow_codes),
            "classification": "HS",
            "frequency": "M",
        },
        "response": {"rows": rows},
    }
    target_storage = storage or LocalStorage()
    period_range = f"{periods[0]}_{periods[-1]}"
    path = target_storage.write_json(
        DataLayer.BRONZE,
        (
            f"un_comtrade/monthly_trade/{reporter_code}/"
            f"{period_range}_{collected_at:%Y%m%dT%H%M%SZ}.json"
        ),
        document,
    )
    return path, len(rows)
