from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

KST = pendulum.timezone("Asia/Seoul")
PROJECT_DIR = "/opt/fair_value"


def batch_task(task_id: str, command: str, timeout_minutes: int) -> BashOperator:
    return BashOperator(
        task_id=task_id,
        bash_command=command,
        cwd=PROJECT_DIR,
        execution_timeout=timedelta(minutes=timeout_minutes),
    )


with DAG(
    dag_id="fair_value_daily_pipeline",
    description="Refresh local inputs, valuations, and post-valuation evaluations.",
    schedule="20 16 * * 1-5",
    start_date=pendulum.datetime(2026, 1, 1, tz=KST),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["fair_value", "local", "daily"],
) as dag:
    market_price = batch_task(
        "market_price_incremental",
        "python -m fair_value.jobs.market_price_batch --mode incremental",
        30,
    )
    opendart = batch_task(
        "opendart_incremental",
        "python -m fair_value.jobs.opendart_batch --mode incremental",
        90,
    )
    financials = batch_task(
        "normalize_financials",
        "python -m fair_value.jobs.financial_batch",
        20,
    )
    economics = batch_task(
        "economic_indicators_incremental",
        "python -m fair_value.jobs.economic_batch --mode incremental",
        45,
    )
    canonical_quality = batch_task(
        "canonical_data_quality",
        "python -m fair_value.jobs.data_quality --scope canonical",
        10,
    )
    asof_dataset = batch_task(
        "build_asof_dataset",
        "python -m fair_value.jobs.asof_dataset",
        15,
    )
    asof_quality = batch_task(
        "asof_data_quality",
        "python -m fair_value.jobs.data_quality --scope asof",
        10,
    )
    benchmarks = batch_task(
        "benchmark_valuation",
        "python -m fair_value.jobs.benchmark_valuation",
        10,
    )
    cycle_rim = batch_task(
        "cycle_rim_valuation",
        "python -m fair_value.jobs.cycle_rim_valuation",
        10,
    )
    benchmark_backtest = batch_task(
        "benchmark_backtest_v0",
        "python -m fair_value.jobs.backtest_v0",
        10,
    )
    cycle_rim_backtest = batch_task(
        "cycle_rim_backtest_v0",
        "python -m fair_value.jobs.cycle_rim_backtest",
        10,
    )
    backtest_report = batch_task(
        "backtest_report_v1",
        "python -m fair_value.jobs.backtest_report",
        10,
    )

    opendart >> financials
    [market_price, financials, economics] >> canonical_quality >> asof_dataset
    asof_dataset >> asof_quality
    asof_quality >> [benchmarks, cycle_rim]
    benchmarks >> benchmark_backtest
    cycle_rim >> cycle_rim_backtest
    [benchmark_backtest, cycle_rim_backtest] >> backtest_report
