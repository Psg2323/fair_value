# 5주차 과제 — 데이터 파이프라인 부하·장애·복구 실험

## 1. 실험 목적과 범위

2026-08-31에 저장된 KIS 1분봉을 Kafka로 재생하고 Spark bounded batch로 처리했다.
외부 API에는 부하를 보내지 않았다. 기준 실행보다 입력을 5배로 늘리고, 중복 실행,
잘못된 이벤트, 처리 중단, 저장 권한 실패를 재현한 뒤 재실행 무결성을 확인했다.

~~~text
KIS Minute Bronze
  → Kafka replay
  → Spark schema/quality validation
  → Silver Parquet + daily market-state feature
~~~

- Python 3.12
- Apache Kafka 4.0.2, KRaft 단일 broker
- Apache Spark 4.0.4, local Docker container
- 입력: 20종목, 2026-08-28 1분봉 7,540건
- 격리 topic: fair_value.market_price.minute.raw.v1.assignment5

## 2. 정상 실행 기준선

시간은 Kafka/Spark 실행 명령의 실제 wall time이며 Spark는 컨테이너 시작을 포함한다.

| 작업 | 처리 건수 | 저장/수신 건수 | 실행 시간 |
|---|---:|---:|---:|
| Kafka Producer | 7,540 | sent 7,540 | 0.22초 |
| Kafka Consumer | 7,540 | received 7,540 | 0.24초 |
| Spark batch | 7,540 | Silver 7,540 / feature 20 | 30.69초 |

## 3. 부하 실행

같은 원천 이벤트를 네 번 추가 재생해 topic 누적 입력을 37,700건으로 늘렸다.
이는 정상 입력의 5배이며 외부 시스템이 아닌 로컬 Kafka만 대상으로 했다.

| 작업 | 처리 건수 | 결과 | 실행 시간 |
|---|---:|---:|---:|
| 추가 Producer | 30,160 | 누적 37,700 | 0.24초 |
| Consumer | 37,700 | received 37,700 | 0.34초 |
| Spark batch | 37,700 | 중복 30,160 제거 / Silver 7,540 | 32.15초 |

입력은 5배가 됐지만 canonical key인 ticker + timestamp로 중복을 제거해 저장
건수는 7,540건으로 유지됐다.

## 4. 장애 재현

### 저장 실패

Spark 컨테이너 UID와 host 출력 디렉터리 권한을 불일치시켜 Parquet write 실패를
재현했다. 출력 권한을 정상화한 뒤 동일 bounded 입력을 다시 실행했다.

### 잘못된 입력

필수 필드 price가 없는 이벤트 10건을 별도 fault injector로 전송했다. Spark는
정상 이벤트와 섞어 저장하지 않고 10건 모두 quarantine으로 분리했다.

### 처리 작업 중단

--fail-before-write 옵션으로 검증·중복 제거 후 최종 저장 직전에 의도적으로
중단했다. 원자적 교체 전 실패이므로 기존 Silver 결과는 손상되지 않았다.

### 중복 실행

동일 이벤트를 반복 전송해 중복 실행을 재현했다. Kafka에는 이벤트가 남지만 Silver에는
canonical key별 한 행만 유지됐다.

## 5. 복구 및 무결성 검증

장애 원인을 제거하고 같은 입력을 다시 실행한 최종 결과는 다음과 같다.

~~~text
input_row_count=37710
invalid_row_count=10
duplicate_removed_count=30160
silver_row_count=7540
silver_unique_keys=7540
feature_row_count=20
quarantine_row_count=10
~~~

중단 전후 집계도 동일했다.

~~~text
price_sum=1703285025
volume_sum=26968318
~~~

따라서 복구 후 정상 데이터 누락과 canonical 중복은 0건이다. 잘못된 10건은
quarantine에 보존돼 원인 확인과 재처리가 가능하다.

## 6. 재현 명령

~~~bash
docker compose up -d kafka

python -m fair_value.coursework.minute_kafka_producer \
  --topic fair_value.market_price.minute.raw.v1.assignment5 \
  --trading-date 20260828
python -m fair_value.coursework.minute_kafka_consumer \
  --topic fair_value.market_price.minute.raw.v1.assignment5 \
  --expected-count 7540

python -m fair_value.coursework.minute_kafka_producer \
  --topic fair_value.market_price.minute.raw.v1.assignment5 \
  --trading-date 20260828 --repeat 4
python -m fair_value.coursework.kafka_fault_injector \
  --topic fair_value.market_price.minute.raw.v1.assignment5 \
  --fault missing_price --count 10

docker compose --profile course run --rm spark \
  /opt/spark/bin/spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  --conf spark.ui.showConsoleProgress=false \
  src/fair_value/coursework/spark_minute_market_batch.py \
  --topic fair_value.market_price.minute.raw.v1.assignment5
~~~

처리 중단은 마지막 Spark 명령에 --fail-before-write를 추가해 재현한다.

## 7. 산출물과 결론

- Silver: data/silver/market_price_minute/canonical.parquet
- 일별 feature: data/gold/features/market_state_daily.parquet
- quarantine: data/silver/quarantine/minute_price/ JSON
- 상세 실험 기록: docs/PIPELINE_RELIABILITY_EXPERIMENT.md

이번 실험에서 Kafka는 원천 이벤트 재생과 중복 실행 재현, Spark는 스키마 적용·품질
검사·중복 제거·Parquet 저장에 사용했다. 하루 7,540건 자체가 분산 처리를 요구하는
규모는 아니며, 이 프로젝트에서의 근거는 처리량보다 재생 가능성, 장애 격리, 멱등
복구를 검증하는 데 있다.
