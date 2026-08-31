from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

KST = pendulum.timezone("Asia/Seoul")
PROJECT_DIR = "/opt/fair_value"


with DAG(
    dag_id="fair_value_trade_cycle_monthly",
    description="Refresh available UN Comtrade monthly semiconductor trade inputs.",
    schedule="30 17 16 * *",
    start_date=pendulum.datetime(2026, 8, 16, tz=KST),
    catchup=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["fair_value", "local", "trade_cycle"],
) as dag:
    BashOperator(
        task_id="collect_and_build_trade_cycle",
        bash_command=(
            "python -m fair_value.jobs.trade_batch --mode incremental --source un_comtrade"
        ),
        cwd=PROJECT_DIR,
        execution_timeout=timedelta(minutes=90),
    )
