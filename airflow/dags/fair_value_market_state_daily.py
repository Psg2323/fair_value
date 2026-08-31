from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

KST = pendulum.timezone("Asia/Seoul")
PROJECT_DIR = "/opt/fair_value"


with DAG(
    dag_id="fair_value_market_state_daily",
    description="Collect 20-stock KIS minute data and publish the session to Kafka.",
    schedule="20 16 * * 1-5",
    start_date=pendulum.datetime(2026, 8, 28, tz=KST),
    catchup=True,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["fair_value", "local", "market_state"],
) as dag:
    collect_and_build = BashOperator(
        task_id="collect_minute_and_build_market_state",
        bash_command=("python -m fair_value.jobs.market_state_batch --target-date '{{ ds }}'"),
        cwd=PROJECT_DIR,
        execution_timeout=timedelta(minutes=45),
    )
    publish_kafka = BashOperator(
        task_id="publish_minute_events_to_kafka",
        bash_command=(
            "python -m fair_value.coursework.minute_kafka_producer "
            "--bootstrap-servers kafka:19092 --trading-date '{{ ds_nodash }}'"
        ),
        cwd=PROJECT_DIR,
        execution_timeout=timedelta(minutes=20),
    )

    collect_and_build >> publish_kafka
