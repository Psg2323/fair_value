FROM apache/airflow:3.3.1-python3.12

COPY --chown=airflow:root pyproject.toml README.md /tmp/fair_value/
COPY --chown=airflow:root src /tmp/fair_value/src

RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" "/tmp/fair_value[course]" \
    && rm -rf /tmp/fair_value

ENV PYTHONPATH=/opt/fair_value/src
