import pytest

from fair_value.features.market_state import derive_daily_market_state
from fair_value.normalization.minute_price import normalize_kis_minute_documents


def row(clock: str, price: str, volume: str) -> dict[str, str]:
    return {
        "stck_bsop_date": "20260831",
        "stck_cntg_hour": clock,
        "stck_prpr": price,
        "cntg_vol": volume,
    }


def test_minute_normalization_and_daily_market_state() -> None:
    document = {
        "source": "kis",
        "ticker": "005930",
        "collected_at": "2026-08-31T07:00:00+00:00",
        "records": [
            row("090000", "100", "10"),
            row("093000", "101", "20"),
            row("150000", "102", "30"),
            row("153000", "999", "40"),
            row("153000", "103", "40"),
            row("120000", "0", "5"),
        ],
    }

    normalized, report = normalize_kis_minute_documents([document])
    features = derive_daily_market_state(normalized)
    result = features.row(0, named=True)

    assert report.input_row_count == 6
    assert report.null_or_type_invalid_count == 1
    assert report.duplicate_removed_count == 1
    assert report.output_row_count == 4
    assert result["minute_count"] == 4
    assert result["open_price"] == 100
    assert result["close_price"] == 103
    assert result["total_volume"] == 100
    assert result["vwap"] == pytest.approx(102)
    assert result["close_vwap_ratio"] == pytest.approx(103 / 102 - 1)
    assert result["opening_volume_ratio"] == pytest.approx(0.1)
    assert result["closing_volume_ratio"] == pytest.approx(0.7)
    assert result["intraday_momentum"] == pytest.approx(0.03)
    assert result["intraday_reversal"] == pytest.approx(0)
