from datetime import date

import pytest

from fair_value.features.trade_cycle import derive_trade_cycle_features
from fair_value.normalization.trade_flows import normalize_trade_documents


def test_trade_normalization_preserves_availability_and_builds_momentum() -> None:
    customs_rows = [
        {
            "year": period,
            "hsCode": "8542",
            "expDlr": str(export),
            "impDlr": "80",
            "expWgt": "10",
            "impWgt": "8",
        }
        for period, export in [
            ("2026.01", 100),
            ("2026.02", 110),
            ("2026.03", 120),
            ("2026.04", 130),
        ]
    ]
    documents = [
        {
            "source": "customs",
            "collected_at": "2026-05-15T01:00:00+00:00",
            "request": {"hs_code": "8542"},
            "response": {"rows": customs_rows},
        },
        {
            "source": "un_comtrade",
            "collected_at": "2026-05-20T01:00:00+00:00",
            "request": {},
            "response": {
                "rows": [
                    {
                        "period": "202604",
                        "reporterCode": 410,
                        "partnerCode": 0,
                        "flowCode": "X",
                        "cmdCode": "8542",
                        "primaryValue": 125,
                        "qty": 0,
                        "lastReleasedAt": "2026-05-18T00:00:00",
                    }
                ]
            },
        },
    ]

    normalized, report = normalize_trade_documents(documents)
    features = derive_trade_cycle_features(normalized)
    customs = features.filter(
        (features["source"] == "customs") & (features["period_end"] == date(2026, 4, 30))
    ).row(0, named=True)
    comtrade = normalized.filter(normalized["source"] == "un_comtrade").row(0, named=True)

    assert report.input_row_count == 5
    assert report.output_row_count == 9
    assert customs["available_at"] == date(2026, 5, 15)
    assert customs["export_momentum_3m"] == pytest.approx(0.3)
    assert comtrade["available_at"] == date(2026, 5, 18)
    assert comtrade["availability_basis"] == "source_last_released_at"
    assert comtrade["partner_code"] == "0"
    assert comtrade["quantity"] == 0.0


def test_trade_normalization_marks_only_latest_observed_snapshot() -> None:
    def document(collected_at: str, value: int) -> dict[str, object]:
        return {
            "source": "un_comtrade",
            "collected_at": collected_at,
            "request": {},
            "response": {
                "rows": [
                    {
                        "period": "202604",
                        "reporterCode": 410,
                        "partnerCode": 0,
                        "flowCode": "X",
                        "cmdCode": "8542",
                        "primaryValue": value,
                    }
                ]
            },
        }

    normalized, report = normalize_trade_documents(
        [
            document("2026-05-20T01:00:00+00:00", 100),
            document("2026-05-21T01:00:00+00:00", 110),
        ]
    )

    assert report.output_row_count == 2
    assert normalized["available_at"].to_list() == [date(2026, 5, 20), date(2026, 5, 21)]
    assert normalized["is_latest_source_snapshot"].to_list() == [False, True]
