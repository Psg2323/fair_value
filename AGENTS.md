# Repository Guidelines

## Working Method

Treat checked-in code, configuration, and the current README as the source of truth. Before implementing, inspect the repository structure and related modules and tests. Extend existing collectors, storage abstractions, and configuration; do not create duplicate implementations. Deliver the smallest coherent change and split large features into reviewable steps.

## Architecture Boundaries

Keep pipeline layers explicit: **Raw → Normalized → Feature → Valuation → Backtest**. Raw preserves source responses and metadata; Normalized produces canonical typed records; Feature derives reusable inputs; Valuation estimates value; Backtest evaluates outputs.

Separate data I/O from financial calculations. Keep API and storage concerns out of calculation modules. Write valuation logic as deterministic, typed pure functions whenever possible. Historical loads and incremental batches must produce the same canonical schema and pass the same validation rules.

The MVP is local-first. Do not introduce AWS, Spark, Kafka, Airflow, or similar infrastructure until a demonstrated requirement and documented decision justify the complexity.

## Financial and Temporal Correctness

Represent the economic period (`period_end`) separately from when information became usable (`available_at` or `filing_date`). Features and backtests may use only data available at each evaluation timestamp. Never use future filings, revisions unavailable at the time, or future-derived features. Look-ahead bias is not acceptable.

Treat Residual Income, normalized FCFF/DCF, relative valuation, and cycle-regime approaches as research candidates, not settled architecture. Selection or combination requires empirical evidence and point-in-time backtesting.

## Project Layout and Style

Use Python 3.12 and the existing `src/fair_value/` layout. Keep integrations in `collectors/`, persistence in `storage/`, configuration in `config/`, and tests under `tests/` mirroring package paths. Use four spaces, a 100-character line limit, standard Python naming, complete type annotations, Ruff, and strict mypy.

## Testing, Commands, and Security

Consider related tests with every code change. Use pytest names such as `test_<behavior>`; mock external APIs, credentials, time delays, and market data. Run `pytest`, `ruff check .`, `ruff format --check .`, and `mypy src` before review.

Read credentials only from `.env` or environment variables. Never hard-code or expose secrets in code, logs, fixtures, screenshots, or commits. Do not commit generated datasets.

## Documentation and Changes

Keep README status separated into **Implemented**, **In Progress**, and **Planned**. Reserve `docs/VALUATION_SPEC.md` for model definitions, inputs, outputs, and assumptions; `docs/DATA_CONTRACT.md` for sources, canonical schemas, and features; `docs/BACKTEST_SPEC.md` for point-in-time, walk-forward, and validation rules; and `docs/DECISIONS.md` for architecture/model decisions and trade-offs. Use focused Conventional Commit subjects such as `feat:`, `fix:`, `test:`, `docs:`, or `chore:`.
