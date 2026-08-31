# 파이프라인 부하·장애·복구 실험

## 환경과 입력

실험은 2026-08-31에 외부 API가 아닌 저장된 KIS Bronze를 재생해 수행했습니다.

- Python 3.12
- Apache Kafka 4.0.2, KRaft 단일 broker
- Apache Spark 4.0.4, local Docker container
- 입력: 20종목의 2026-08-28 1분봉 7,540건
- 격리 topic: `fair_value.market_price.minute.raw.v1.assignment5`

## 기준선과 부하 결과

모든 시간은 의존성 확인과 컨테이너 시작을 포함한 실제 wall time입니다.

| 실행 | 입력 | 출력 | 시간 |
|---|---:|---:|---:|
| 기준 Producer | 7,540 | sent 7,540 | 0.22초 |
| 기준 Consumer | 7,540 | received 7,540 | 0.24초 |
| 기준 Spark | 7,540 | Silver 7,540, feature 20 | 30.69초 |
| 부하 Producer | 추가 30,160 | 누적 37,700 | 0.24초 |
| 부하 Consumer | 37,700 | received 37,700 | 0.34초 |
| 부하 Spark | 37,700 | 중복 30,160 제거, Silver 7,540 | 32.15초 |

재현 명령은 다음과 같습니다.

```bash
python -m fair_value.coursework.minute_kafka_producer --topic fair_value.market_price.minute.raw.v1.assignment5 --trading-date 20260828
python -m fair_value.coursework.minute_kafka_consumer --topic fair_value.market_price.minute.raw.v1.assignment5 --expected-count 7540
python -m fair_value.coursework.minute_kafka_producer --topic fair_value.market_price.minute.raw.v1.assignment5 --trading-date 20260828 --repeat 4
python -m fair_value.coursework.minute_kafka_consumer --topic fair_value.market_price.minute.raw.v1.assignment5 --expected-count 37700
docker compose --profile course run --rm spark /opt/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 --conf spark.jars.ivy=/tmp/.ivy2 --conf spark.ui.showConsoleProgress=false src/fair_value/coursework/spark_minute_market_batch.py --topic fair_value.market_price.minute.raw.v1.assignment5
```

## 장애 재현

1. 저장 실패: Spark UID와 host directory 권한 불일치로 Parquet write가 실패했습니다.
2. 잘못된 입력: `price`가 없는 이벤트 10건을 추가해 quarantine 분기를 확인했습니다.
3. 처리 중단: `--fail-before-write`로 출력 직전에 의도적으로 작업을 중단했습니다.

장애 주입 명령은 다음과 같습니다.

```bash
python -m fair_value.coursework.kafka_fault_injector --topic fair_value.market_price.minute.raw.v1.assignment5 --fault missing_price --count 10
docker compose --profile course run --rm spark /opt/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 --conf spark.jars.ivy=/tmp/.ivy2 --conf spark.ui.showConsoleProgress=false src/fair_value/coursework/spark_minute_market_batch.py --topic fair_value.market_price.minute.raw.v1.assignment5 --fail-before-write
```

## 복구와 무결성 검증

권한을 수정하고 같은 bounded Kafka 입력을 재실행한 결과는 다음과 같습니다.

```text
input_row_count=37710
invalid_row_count=10
duplicate_removed_count=30160
silver_row_count=7540
silver_unique_keys=7540
feature_row_count=20
quarantine_row_count=10
```

중단 전후 `price_sum=1703285025`, `volume_sum=26968318`도 동일했습니다.

## 결론

외부 서비스에는 부하를 보내지 않았고, 저장된 이벤트만 5배로 재생했습니다.
잘못된 입력은 격리되고 재생 중복은 제거되며, 중단 전 출력과 복구 출력이 일치했습니다.
