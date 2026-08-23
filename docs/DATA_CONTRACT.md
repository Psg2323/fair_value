# Data Contract

## Layer Boundaries

Raw API responses and source metadata live under `data/bronze/`. Canonical typed records live
under `data/silver/`. Reusable inputs and model outputs live under `data/gold/`. Historical and
incremental loads must write the same canonical schema.

## Canonical Datasets

| Dataset | Key | Temporal fields | Current coverage |
| --- | --- | --- | --- |
| `silver/market_price/canonical.parquet` | ticker, trading_date | trading_date | 14,906 rows; 005930 from 1996-08-20, 000660 from 1996-12-26, through 2026-08-24 |
| `silver/financials/canonical.parquet` | ticker, period_end, report_code | period_end, available_at | 86 rows; 2015-12-31 to 2026-06-30 |
| `silver/economic_indicators/canonical.parquet` | source, indicator_id, period_end | period_end, available_at | 10,720 rows; ECOS/KOSIS/FRED from 2015, subject to source coverage |
| `gold/model_inputs/valuation_asof_monthly.parquet` | ticker, valuation_date | valuation_date plus source availability | 250 rows |
| `gold/valuation/benchmark_valuations.parquet` | ticker, valuation_date, model_name | financial period/availability | 466 rows |
| `gold/valuation/fair_value_range.parquet` | ticker, valuation_date | financial period/availability | 188 rows |
| `gold/backtest/reports/combined_results.parquet` | model, ticker, valuation_date, horizon | valuation plus future evaluation dates | 2,616 rows |
| `gold/research/cycle_rim_v1/sensitivity_ranges.parquet` | variant, ticker, valuation_date | financial period/availability | 1,692 rows |

Market Price requires typed OHLCV, unique `ticker + trading_date`, valid
`low <= open/close <= high`, `daily_return`, and `adjusted=true`. Financial inputs preserve
reporting period and filing availability separately. Per-share models use
`equity_per_price_basis_share` and `earnings_per_price_basis_share_ttm`; these use parent equity
and total distributed common plus preferred shares and are not Samsung common-only BVPS.

`config/corporate_actions.yaml` is the source of truth for price-unit conversions. Reported share
counts remain unchanged. The feature layer multiplies pre-effective-date shares by later split
multipliers so per-share financials match KIS ex-post adjusted prices. Every material adjacent
share-count jump must match an explicit action.

## Availability Rules

A model row may join the latest economic period whose observation was available by the valuation
date. A late correction to an older period must not replace a newer period on the availability
frontier. OpenDART and KOSIS currently retain important latest-snapshot limitations described in
the README; neither may be backfilled before its stored availability date. FRED model inputs use
ALFRED initial-release observations.

The `data_quality` job rejects duplicate keys, invalid OHLCV/returns, non-adjusted market
prices, uncovered share-count jumps, invalid per-share calculations, temporal violations, and
future as-of availability. Four initial Samsung share-count nulls remain warnings and are excluded
from per-share valuations.

Generated datasets, Bronze payloads, and credentials are local artifacts and are not committed.
