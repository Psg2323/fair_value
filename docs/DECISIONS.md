# Decisions

## 2026-08-24 - Local Airflow for KIS Daily Price Scheduling

### Context

The local Windows/WSL machine is not always running. KIS daily prices should be collected
after the Korean market close, and missed days must be recovered when the machine next starts.

### Decision

Use Apache Airflow 3.3.1 on Python 3.12 as a Docker Compose `orchestration` profile.

- Schedule the KIS task in `fair_value_daily_pipeline` at 16:20 Asia/Seoul on weekdays.
- Use `catchup=False`; after downtime, create only the latest scheduled run.
- Let the idempotent KIS incremental job recover every date after the last canonical trading day.
- Exclude the current date before 16:10 Asia/Seoul, including manual or startup execution.
- Use `restart: unless-stopped` so the container returns when Docker Desktop starts.
- Keep Kafka and Spark outside this operating path; they remain course adapters.

### Consequences

This is a single-machine local deployment using Airflow standalone and its local metadata store,
not a high-availability production installation. Docker Desktop must start at Windows sign-in.
Move to a multi-service Airflow deployment and external database only when concurrency,
reliability, or remote operation requires it.

## 2026-08-24 - Daily Local Pipeline Scope

### Decision

Keep one weekday 16:20 Asia/Seoul DAG for KIS incremental prices, recent OpenDART refresh,
economic indicators, normalization, as-of inputs, valuation, and post-valuation evaluation.
OpenDART routine runs refresh the current and previous business years; explicit historical mode
remains available. Kafka and Spark are not part of this operating path.

### Consequences

One failed source blocks downstream calculations rather than publishing partially refreshed model
outputs. The local machine and Docker Desktop remain operational dependencies.

## 2026-08-24 - Cycle-Normalized RIM Remains research_v0

### Decision

Implement a finite-fade RIM as a reproducible research candidate, not a selected model. Use the
point-in-time rolling ROE median, a bounded countercyclical adjustment from ALFRED initial-release
U.S. semiconductor production and producer-price signals, and explicit parameter scenarios.
Exclude KOSIS from historical model rows until original vintages are available.

### Consequences

The implementation produces `fair_value_low/base/high`, but those values are experimental.
Initial V/P correlations and range coverage do not support promotion. Fixed ERP, beta, retention,
fade, and scenario widths require sensitivity analysis and walk-forward comparison with Book Value
and no-growth RIM. Samsung consolidated equity also requires eventual SOTP analysis.

## 2026-08-24 - Adjusted-Price Share Basis

### Decision

Keep OpenDART reported shares unchanged and derive separate price-basis shares for per-share
valuation inputs. KIS history is adjusted, so Samsung financial periods before the 2018-05-04
split-share listing multiply reported shares by 50. The action is explicit in
`config/corporate_actions.yaml` and backed by
[Samsung IR](https://www.samsung.com/global/ir/reports-disclosures/public-disclosure-view.71265/).

### Consequences

The conversion removes a roughly 50x pre-split BVPS/EPS unit mismatch. A later-known split is used
only to express historical numerator and denominator in the same units as the adjusted price; it
does not enter earnings or valuation assumptions. Material share-count jumps without a configured
action fail validation.

## 2026-08-24 - Fail-Fast Quality Gates and Backtest Report v1

### Decision

Run canonical quality checks before as-of construction and point-in-time checks before valuation.
Report monthly and non-overlapping samples separately by ticker, year, and horizon. Keep pending
future horizons instead of dropping them.

### Consequences

Invalid adjusted-price basis, keys, OHLCV/returns, financial timing, per-share calculations, or
future availability blocks downstream Airflow tasks. Report v1 reduces hidden dependence from
overlapping windows but does not create statistical significance from the two-company sample.

## 2026-08-24 - Sensitivity Is Diagnostic, Not Parameter Selection

### Decision

Use nine predeclared one-at-a-time cycle-RIM variants. Keep assumptions fixed across annual
2021-2026 walk-forward folds and label the method
`fixed_assumptions_no_selection`. Do not select a variant from future-return results.

### Consequences

The outputs expose assumption sensitivity and time instability without claiming an optimized
model. Research v1 remains outside the daily Airflow model-selection path and does not promote
cycle RIM beyond candidate status.
