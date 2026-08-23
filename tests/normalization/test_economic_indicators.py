from datetime import date

import polars as pl
import pytest

from fair_value.features.cycle import (
    derive_global_semiconductor_cycle_features,
    derive_semiconductor_cycle_features,
)
from fair_value.normalization.economic_indicators import normalize_economic_indicators


def test_normalization_preserves_availability_rules() -> None:
    documents = [
        {
            "source": "ecos",
            "collected_at": "2026-03-02T00:00:00+00:00",
            "request": {
                "indicator_id": "bok_base_rate",
                "stat_code": "722Y001",
                "item_code": "0101000",
                "frequency": "D",
            },
            "response": {"rows": [{"TIME": "20260115", "DATA_VALUE": "2.5"}]},
        },
        {
            "source": "kosis",
            "collected_at": "2026-03-02T00:00:00+00:00",
            "request": {
                "indicator_id": "semiconductor_production_index",
                "org_id": "101",
                "table_id": "DT_1F02001",
                "item_code": "T10",
                "region_code": "00",
                "industry_code": "C261",
                "frequency": "M",
                "availability_lag_days": 35,
            },
            "response": {
                "rows": [
                    {
                        "PRD_DE": "202601",
                        "DT": "120.0",
                        "LST_CHN_DE": "20260310",
                    }
                ]
            },
        },
        {
            "source": "fred",
            "collected_at": "2026-03-02T00:00:00+00:00",
            "request": {
                "indicator_id": "us_semiconductor_industrial_production",
                "series_id": "IPG3344S",
                "frequency": "M",
                "configured_unit": "index_2017_100",
                "vintage_mode": "initial_release",
            },
            "response": {
                "rows": [
                    {
                        "date": "2026-01-01",
                        "realtime_start": "2026-02-18",
                        "realtime_end": "2026-03-17",
                        "value": "151.25",
                    }
                ]
            },
        },
    ]
    frame, report = normalize_economic_indicators(documents)
    ecos = frame.filter(pl.col("source") == "ecos").row(0, named=True)
    kosis = frame.filter(pl.col("source") == "kosis").row(0, named=True)
    fred = frame.filter(pl.col("source") == "fred").row(0, named=True)
    assert ecos["available_at"] == date(2026, 1, 15)
    assert kosis["period_end"] == date(2026, 1, 31)
    assert kosis["available_at"] == date(2026, 3, 10)
    assert fred["period_end"] == date(2026, 1, 31)
    assert fred["available_at"] == date(2026, 2, 18)
    assert fred["is_latest_source_snapshot"] is False
    assert report.invalid_value_count == 0


def test_cycle_features_do_not_use_future_months() -> None:
    rows = []
    for index in range(13):
        period_end = date(2025 + index // 12, index % 12 + 1, 28)
        for indicator, value in (
            ("semiconductor_production_index", 100.0 + index),
            ("semiconductor_shipment_index", 90.0 + index),
            ("semiconductor_inventory_index", 80.0 + index),
        ):
            rows.append(
                {
                    "indicator_id": indicator,
                    "source": "kosis",
                    "period_end": period_end,
                    "available_at": period_end,
                    "value": value,
                }
            )
    full = derive_semiconductor_cycle_features(pl.DataFrame(rows))
    truncated = derive_semiconductor_cycle_features(pl.DataFrame(rows[:-3]))
    assert full.row(-2, named=True) == truncated.row(-1, named=True)
    assert full.row(-1, named=True)["semiconductor_production_yoy"] == pytest.approx(0.12)


def test_global_cycle_features_use_only_initial_release_history() -> None:
    rows = []
    for index in range(13):
        period_end = date(2025 + index // 12, index % 12 + 1, 28)
        for indicator, value in (
            ("us_semiconductor_industrial_production", 100.0 + index),
            ("us_semiconductor_capacity_utilization", 75.0 + index * 0.1),
            ("us_semiconductor_producer_price_index", 200.0 + index),
        ):
            rows.append(
                {
                    "indicator_id": indicator,
                    "source": "fred",
                    "period_end": period_end,
                    "available_at": period_end,
                    "value": value,
                }
            )
    features = derive_global_semiconductor_cycle_features(pl.DataFrame(rows))
    latest = features.row(-1, named=True)
    assert latest["us_semiconductor_industrial_production_yoy"] == pytest.approx(0.12)
    assert latest["us_semiconductor_producer_price_index_yoy"] == pytest.approx(0.06)
    assert latest["us_semiconductor_capacity_utilization_yoy_change"] == pytest.approx(1.2)
