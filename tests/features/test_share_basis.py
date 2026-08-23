from datetime import date

import polars as pl
import pytest

from fair_value.features.share_basis import (
    StockSplit,
    add_price_basis_share_features,
    detect_material_share_count_jumps,
    validate_stock_split_coverage,
)


def _financials() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ticker": ["005930", "005930"],
            "period_end": [date(2018, 3, 31), date(2018, 6, 30)],
            "total_shares_outstanding": [100.0, 5_000.0],
            "equity_parent": [1_000_000.0, 1_050_000.0],
            "net_income_parent_ttm": [100_000.0, 110_000.0],
        }
    )


def _split() -> StockSplit:
    return StockSplit(
        ticker="005930",
        effective_date=date(2018, 5, 4),
        share_multiplier=50.0,
    )


def test_price_basis_features_apply_split_only_to_pre_effective_periods() -> None:
    result = add_price_basis_share_features(_financials(), (_split(),))

    assert result["price_basis_share_adjustment_factor"].to_list() == [50.0, 1.0]
    assert result["price_basis_total_shares_outstanding"].to_list() == [5_000.0, 5_000.0]
    assert result["equity_per_price_basis_share"].to_list() == [200.0, 210.0]
    assert result["earnings_per_price_basis_share_ttm"].to_list() == [20.0, 22.0]


def test_share_count_jump_is_covered_by_configured_split() -> None:
    jumps = validate_stock_split_coverage(_financials(), (_split(),))

    assert jumps == detect_material_share_count_jumps(_financials())
    assert len(jumps) == 1
    assert jumps[0].ratio == pytest.approx(50.0)


def test_unconfigured_material_share_count_jump_is_rejected() -> None:
    with pytest.raises(ValueError, match="Uncovered material share-count jumps"):
        validate_stock_split_coverage(_financials(), ())


def test_later_split_adjusts_every_earlier_financial_period() -> None:
    future_split = StockSplit(
        ticker="005930",
        effective_date=date(2020, 1, 1),
        share_multiplier=2.0,
    )

    result = add_price_basis_share_features(_financials(), (future_split,))

    assert result["price_basis_share_adjustment_factor"].to_list() == [2.0, 2.0]
