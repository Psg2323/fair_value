# Backtest Specification

## v0 Boundary

Valuation and evaluation are separate stages. The valuation interface contains at least
`valuation_date`, `ticker`, `market_price`, and `model_value`. Model calculations may use
only point-in-time inputs available on or before `valuation_date`.

Future prices enter only after model values are frozen. For 1, 3, 6, and 12 calendar months, v0
sets a target date and selects the first trading close on or after that date. If the horizon has
not occurred, the row remains pending with null future price and return.

## Outputs

The evaluation adds `target_date`, `horizon_months`, `future_trading_date`,
`future_price`, and `future_return`. Range models also receive
`future_price_within_range`. Coverage is a calibration diagnostic; it does not make market price
the ground truth for intrinsic value.

Report v1 writes standardized, ticker/horizon, year/horizon, ticker/year/horizon, and
non-overlapping outputs under `data/gold/backtest/reports/`. A non-overlapping series selects the
next valuation only when it starts on or after the prior target or realized future trading date.

## Fixed-Assumption Walk-Forward v1

Sensitivity variants are declared before evaluation and are never selected using future returns.
After three initial calendar years, each later year is reported as a test fold with an expanding
training boundary. The current method is explicitly `fixed_assumptions_no_selection`; it measures
time stability but does not estimate parameters.

## Model-Selection Criteria

A candidate must first have zero point-in-time and look-ahead violations. Compare it with Book
Value and no-growth RIM using:

- coverage, missingness, and sensitivity to assumptions;
- stability of the V/P relationship with later 1M/3M/6M/12M returns;
- low/base/high coverage and width, by ticker and cycle condition;
- walk-forward performance versus benchmarks, with parameters fixed before each test window;
- accounting consistency, interpretability, and failure behavior.

The current two-ticker sample cannot establish sector-wide generalization or reliable statistical
significance. Report v1 exposes overlapping and non-overlapping results separately, but 12M
non-overlapping samples remain very small. Preserve source vintages and add firms before selecting
a model.
