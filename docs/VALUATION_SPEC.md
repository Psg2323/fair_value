# Valuation Specification

## Status and Objective

The implemented model is `research_v0`, not a validated production valuation or investment
recommendation. It estimates an explainable intrinsic-value range for Samsung Electronics and
SK hynix. Market price is used only to calculate V/P and post-valuation diagnostics; it is not an
intrinsic-value label.

## Point-in-Time Inputs

Each row is keyed by `ticker + valuation_date` and may use only records whose
`available_at <= valuation_date`. The current model requires:

- parent equity per KIS adjusted-price share unit and its financial `period_end/available_at`;
- the point-in-time rolling median of reported TTM ROE;
- the available Korean Treasury 3-year yield;
- ALFRED initial-release U.S. semiconductor industrial-production YoY and producer-price YoY.

KIS history is ex-post split-adjusted. Reported shares remain unchanged for audit, while explicit
corporate actions convert them to `price_basis_total_shares_outstanding`. Samsung periods before
the 2018-05-04 listing of split shares use a 50x factor. This is a unit conversion, not predictive
information.

KOSIS signals are excluded from historical model runs because the stored historical observations
are a latest-vintage snapshot with 2026 availability. Capacity utilization is excluded because its
initial-release history begins only in 2022.

## Benchmarks

Book Value uses `V = B`. No-growth RIM uses `RI = EPS - k_e * B` and
`V = B + RI / k_e`. Both are comparison models, not truth labels.

## Cycle-Normalized RIM research_v0

The bounded cycle score is:

`s = 0.5 * [clip(IP_yoy / 0.10, -1, 1) + clip(PPI_yoy / 0.10, -1, 1)]`

The base normalized ROE is the rolling ROE median minus `0.02 * s`, bounded to 0%-30%.
This makes the assumption modestly countercyclical; the cycle score does not predict price.

Cost of equity is `clip(r_f + beta * ERP, 6%, 20%)`, with beta 1.0 and base ERP 5.5%.
For five forecast years, excess ROE fades linearly to zero. Opening book value follows clean
surplus with a research retention assumption of 50%. Value equals opening book plus discounted
forecast residual income; no separate terminal residual income is added after the fade.

The range is parameter sensitivity, not a confidence interval:

| Scenario | Normalized ROE | ERP |
| --- | ---: | ---: |
| low | base - 2pp | base + 1.5pp |
| base | unchanged | unchanged |
| high | base + 2pp | base - 1.5pp |

## Sensitivity and Walk-Forward research_v1

`config/valuation_sensitivity.yaml` declares nine one-at-a-time variants: base, two fade
horizons, two retention ratios, two cycle-adjustment bounds, and two ERP changes. Each variant
changes one assumption while all others remain fixed. The run does not rank or select variants
using future returns.

Walk-forward v1 reserves the first three calendar years, then reports annual 2021-2026 evaluation
folds with `walk_forward_method=fixed_assumptions_no_selection`. It is an expanding-time
diagnostic, not a fitted or tuned model.

## Current Evidence and Limitations

The 2026-08-24 run produced 188 monthly `research_v0` ranges from 2018-11 through 2026-08.
Report v1 separates monthly and non-overlapping horizon samples. Non-overlapping range coverage
is about 14%-18%, and the V/P relationship changes sign by ticker and horizon. Only 14 base rows
are evaluated at the non-overlapping 12M horizon.

Sensitivity v1 produced 1,692 ranges. Latest values varied by roughly -5% to +5% around base, but
the sample is too small to select an assumption set. The sample contains only two related Korean
firms, and Samsung is valued on consolidated equity despite non-semiconductor businesses. Future
work must address source vintages, company-specific assumptions, broader firms, and Samsung SOTP
before model selection.

## References

- [Ohlson (1995), Earnings, Book Values, and Dividends in Equity Valuation](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1911-3846.1995.tb00461.x)
- [Federal Reserve G.17 methodology](https://www.federalreserve.gov/releases/g17/about.htm)
- [Damodaran, normalized earnings for cyclical firms](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/normearn.htm)
