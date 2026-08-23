from datetime import date

import polars as pl

from fair_value.backtest.walk_forward import (
    assign_fixed_assumption_walk_forward_folds,
)


def test_fixed_assumption_walk_forward_reserves_later_years_for_evaluation() -> None:
    frame = pl.DataFrame(
        {
            "valuation_date": [
                date(2018, 12, 31),
                date(2019, 12, 31),
                date(2020, 12, 31),
                date(2021, 12, 31),
                date(2022, 12, 31),
            ],
            "ticker": ["005930"] * 5,
            "future_return": [0.1] * 5,
        }
    )

    result = assign_fixed_assumption_walk_forward_folds(
        frame,
        initial_training_years=3,
    )

    assert result["test_year"].to_list() == [2021, 2022]
    assert result["training_end_date"].to_list() == [
        date(2020, 12, 31),
        date(2021, 12, 31),
    ]
    assert result["walk_forward_method"].unique().to_list() == ["fixed_assumptions_no_selection"]
