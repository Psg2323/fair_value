# 반도체 Fundamental Fair Value 프로젝트

## 프로젝트 개요

기업의 fundamental data와 반도체 산업 사이클을 결합해 intrinsic fair value range를
산정하고, point-in-time·walk-forward 방식으로 유효성을 검증하는 local-first 프로젝트입니다.

## 분석 대상

가치평가 MVP와 시장 데이터 수집 범위를 구분합니다.

| 단계 | 분류 | 대상 기업 |
|---|---|---|
| 가치평가 MVP | 메모리 반도체 | 삼성전자, SK하이닉스 |
| 시장 데이터 | 반도체·장비 | DB하이텍, LX세미콘, 제주반도체, 한미반도체, HPSP, 원익IPS, 주성엔지니어링, 유진테크, 테스, PSK, 이오테크닉스, 테크윙 |
| 시장 데이터 | 소재·부품·후공정 | 솔브레인, 동진쎄미켐, 티씨케이, 하나마이크론, 리노공업, ISC |

## 목표 출력

```text
fundamental·cycle 입력 → fair_value_low/base/high → point-in-time backtest
```

단기 주가를 직접 예측하거나 시장가격을 intrinsic value의 정답으로 사용하지 않습니다.

- 현재 주가와 적정가치 low/base/high 비교
- 가치평가 premium·discount 추이
- ROE, 영업이익률, 재고 증가율, CAPEX와 FCF proxy
- 기준금리, 국고채 금리와 원/달러 환율
- 국내외 반도체 생산·출하·재고·가동률 지표
- 기간별 backtest 성과와 모델 진단 결과

## 현재 진행 상태

### 구현 완료

가치평가 결과와 backtest는 삼성전자·SK하이닉스에 한정됩니다.

- KIS 20종목 일봉 61,787건과 2026-08-28 1분봉 7,540건 수집·정규화
- OpenDART raw collector와 수집 함수, ECOS·KOSIS·FRED 수집 파이프라인
- 평가 당시 공개된 정보만 사용하는 분석 데이터 생성
- Book Value·no-growth RIM benchmark와 연구용 cycle-RIM 범위
- 1M·3M·6M·12M point-in-time backtest 및 walk-forward 보고
- Airflow 배치 자동화와 데이터·코드 품질 검사
- Kafka 4.0.2 replay와 Spark 4.0.4 정규화·중복 제거·Parquet 저장
- 20종목 일별 market-state feature와 valuation-gap snapshot
- UN Comtrade 반도체 무역 3,105개 빈티지(경제 키 3,078개)와 trade-cycle feature 516행

### 개발·검토 중

- 관세청 품목별 수출입 API 활용신청 승인과 최초 historical load
- trade-cycle feature와 기존 cycle signal 결합 검증
- 적정가치 가정의 안정성·설명력 검증
- OpenDART 정정 전 원공시 버전 보존
- Airflow에서 Kafka 이후 Spark 실행을 연결하는 운영 방식 검토

### 향후 구현 예정

- cycle-normalized RIM의 사전 명세와 추가 regime 검증
- 삼성전자 사업부별 SOTP
- 해외 반도체 기업 확장
- 배치 실행 알림과 운영 모니터링 고도화

## 데이터 흐름 아키텍처

```text
KIS / OpenDART / ECOS / KOSIS / FRED / Customs / UN Comtrade
                              │
                              ▼
                       Bronze (원천)
                              │
                              ▼
                    Silver (canonical)
                              │
                              ▼
                Gold (feature / as-of dataset)
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
       Valuation / Backtest        Cycle / Market State

KIS minute Bronze → Kafka replay → Spark batch → Silver / daily feature
```

### 주요 결과물

| 구분 | 경로 | 내용 |
|---|---|---|
| 시장가격 | `data/silver/market_price/canonical.parquet` | 수정주가 OHLCV |
| 재무정보 | `data/silver/financials/canonical.parquet` | point-in-time 재무·주식 수·배당 |
| 경제지표 | `data/silver/economic_indicators/canonical.parquet` | 금리·환율·반도체 산업지표 |
| 1분봉 | `data/silver/market_price_minute/canonical.parquet` | KIS 체결가·분당 거래량 |
| 무역 | `data/silver/trade_flows/canonical.parquet` | UN Comtrade 월별 HS 무역 3,105개 빈티지(경제 키 3,078개); 관세청 승인 대기 |
| 재무 feature | `data/gold/features/fundamental_features.parquet` | ROE·마진·재고·CAPEX·FCF proxy |
| 시장 feature | `data/gold/features/market_state_daily.parquet` | VWAP·실현변동성·거래량 집중도 |
| 무역 cycle | `data/gold/features/trade_cycle_features.parquet` | 수출입·무역수지·YoY·3개월 momentum 516행 |
| 모델 입력 | `data/gold/model_inputs/valuation_asof_monthly.parquet` | 월말 기준 as-of 데이터 |
| 적정가치 | `data/gold/valuation/fair_value_range.parquet` | 기업별 low·base·high 범위 |
| 검증 결과 | `data/gold/backtest/` | 기간별 backtest 및 report |

### 저장소 구조

```text
config/                 기업·계정 매핑
data/bronze/            원천 데이터
data/silver/            정규화 데이터
data/gold/              feature·valuation·backtest 결과
src/fair_value/         수집·정규화·계산·배치 코드
airflow/                로컬 스케줄러와 DAG
docs/                   데이터·모델·검증 명세
tests/                  자동화 테스트
```

상세 설계와 연구 가정은 다음 문서에서 관리합니다.

- `docs/DATA_CONTRACT.md`: 데이터 스키마와 이용 가능 시점 규칙
- `docs/VALUATION_SPEC.md`: 가치평가 입력·수식·가정
- `docs/BACKTEST_SPEC.md`: point-in-time 검증 기준
- `docs/DECISIONS.md`: 주요 설계 결정과 trade-off

---

## 4차시 과제: Kafka·Spark 데이터 처리

> 운영 데이터와 동일한 canonical 규칙을 사용하는 Kafka replay·Spark batch 검증입니다.

### 1. 데이터·메시지 명세

KIS에서 수집한 삼성전자와 SK하이닉스의 일별 주가 데이터를 Kafka 메시지로 전송했습니다.

#### Kafka 메시지 필드

| 필드명 | JSON 타입 | 의미 |
|---|---|---|
| `ticker` | String | 종목코드(`005930`, `000660`) |
| `trading_date` | String | 거래일, `yyyyMMdd` 형식 |
| `open` | String | 시가 |
| `high` | String | 고가 |
| `low` | String | 저가 |
| `close` | String | 종가 |
| `volume` | String | 거래량 |
| `source` | String | 데이터 출처, 현재 값은 `kis` |
| `adjusted` | Boolean | 수정주가 적용 여부 |

KIS 원천값을 보존하기 위해 가격과 거래량은 Kafka 전송 단계에서 문자열로 전달하고, Spark 전처리 과정에서 숫자 타입으로 변환했습니다.

#### Kafka 메시지 Key

```text
ticker:trading_date
```

예시:

```text
000660:20240729
```

#### Kafka JSON 예시

```json
{
  "ticker": "000660",
  "trading_date": "20240729",
  "open": "195000",
  "high": "195700",
  "low": "192200",
  "close": "195600",
  "volume": "4017366",
  "source": "kis",
  "adjusted": true
}
```

#### Kafka Topic

```text
fair_value.market_price.raw.v1
```

- Kafka 버전: Apache Kafka 4.0.2
- 실행 방식: KRaft 단일 Broker
- 접속 주소: `localhost:29092`

### 2. Kafka 이벤트 전송 및 수신

#### Kafka 실행

```bash
docker compose up -d kafka
```

#### Producer 실행

KIS Bronze 데이터에서 거래일과 종목코드 순으로 정렬한 후 최신 1,000건을 Kafka로 전송합니다.

```bash
python -m fair_value.coursework.kafka_producer --limit 1000
```

Producer 출력:

```text
topic=fair_value.market_price.raw.v1
requested_count=1000
sent_count=1000
```

`sent_count`는 Kafka Broker가 정상 수신을 확인한 메시지만 집계합니다.

#### Consumer 실행

```bash
python -m fair_value.coursework.kafka_consumer --expected-count 1000
```

Consumer 출력:

```text
topic=fair_value.market_price.raw.v1
received_count=1000
```

Consumer는 다음 내용을 검증했습니다.

- 메시지 값이 null이 아닌지 확인
- 메시지가 정상적인 JSON 객체인지 확인
- 필수 필드 9개가 모두 포함되어 있는지 확인
- 제한 시간 안에 1,000건을 모두 수신했는지 확인

#### Kafka 처리 결과

| 항목 | 건수 |
|---|---:|
| Producer 요청 | 1,000건 |
| Kafka 전송 성공 | 1,000건 |
| Consumer 수신 성공 | 1,000건 |
| 전송 실패 | 0건 |

### 3. Spark 전처리 및 저장

Kafka로 전송한 것과 동일한 JSON 구조를 Spark 4.0.4 배치 작업으로 처리했습니다.

#### Spark 실행 명령

```bash
docker compose --profile course run --rm spark \
  /opt/spark/bin/spark-submit \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  src/fair_value/coursework/spark_market_price_batch.py
```

Spark는 Kafka Topic의 `earliest`부터 `latest`까지 데이터를 읽는 배치 방식으로 동작합니다.

#### 전처리 내용

1. Kafka 메시지의 JSON 구조 해석
2. 종목코드와 출처의 앞뒤 공백 제거
3. `trading_date`를 Date 타입으로 변환
4. OHLC와 거래량을 Int64 타입으로 변환
5. 필수 필드의 null 및 타입 오류 검사
6. 시가·고가·저가·종가와 거래량 유효성 검사
7. `ticker + trading_date` 기준 중복 제거
8. 종목별 전일 종가 대비 일간 수익률 계산
9. 결과를 Snappy 압축 Parquet 형식으로 저장

OHLC 데이터는 다음 조건으로 검증했습니다.

```text
open > 0
high > 0
low > 0
close > 0
volume >= 0
high >= open, low, close
low <= open, high, close
```

일간 수익률 계산식:

```text
daily_return = close / previous_close - 1
```

종목별 첫 거래일은 이전 종가가 없으므로 `daily_return`이 null입니다.

#### Spark 처리 결과

| 항목 | 건수 |
|---|---:|
| Kafka 입력 | 1,000건 |
| JSON 해석 성공 | 1,000건 |
| null 또는 타입 오류 | 0건 |
| OHLC 오류 | 0건 |
| 제거된 중복 | 0건 |
| 최종 출력 | 1,000건 |

실제 저장 결과는 삼성전자 500건, SK하이닉스 500건으로 총 1,000건입니다.

```text
데이터 기간: 2024-07-29 ~ 2026-08-20
```

#### 최종 컬럼

| 컬럼명 | Spark 타입 | 의미 |
|---|---|---|
| `ticker` | String | 종목코드 |
| `trading_date` | Date | 거래일 |
| `open` | Long | 시가 |
| `high` | Long | 고가 |
| `low` | Long | 저가 |
| `close` | Long | 종가 |
| `volume` | Long | 거래량 |
| `daily_return` | Double | 전일 종가 대비 일간 수익률 |
| `source` | String | 데이터 출처 |
| `adjusted` | Boolean | 수정주가 적용 여부 |

최종 Spark Schema:

```text
struct<
  ticker:string,
  trading_date:date,
  open:bigint,
  high:bigint,
  low:bigint,
  close:bigint,
  volume:bigint,
  daily_return:double,
  source:string,
  adjusted:boolean
>
```

#### 저장 위치와 형식

프로젝트 저장 위치:

```text
data/silver/market_price/course_exercise/
```

Spark 컨테이너 내부 위치:

```text
/opt/fair_value/data/silver/market_price/course_exercise
```

저장 형식:

```text
Apache Parquet + Snappy 압축
```

Spark는 여러 개의 `part-*.snappy.parquet` 파일과 작업 완료를 나타내는 `_SUCCESS` 파일을 생성합니다. 작업을 다시 실행하면 기존 결과를 덮어씁니다.

## 로컬 실행

Python 3.12와 Docker Desktop이 필요합니다. 인증정보는 `.env`에만 둡니다.

```bash
cp .env.example .env
python -m pip install -e '.[dev,course]'
docker compose up -d kafka
```

### 20종목 일봉·1분봉

```bash
python -m fair_value.jobs.market_price_batch --mode incremental
python -m fair_value.jobs.market_state_batch --target-date 2026-08-28
```

두 작업은 재실행해도 canonical key 기준으로 중복을 남기지 않습니다.

### Kafka replay와 Spark batch

```bash
python -m fair_value.coursework.minute_kafka_producer --trading-date 20260828
python -m fair_value.coursework.minute_kafka_consumer --expected-count 7540
docker compose --profile course run --rm spark /opt/spark/bin/spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 --conf spark.jars.ivy=/tmp/.ivy2 --conf spark.ui.showConsoleProgress=false src/fair_value/coursework/spark_minute_market_batch.py
```

### 반도체 무역 cycle

```bash
python -m fair_value.jobs.trade_batch \
  --mode historical --source un_comtrade --start-date 2015-01-01
# 관세청 API 활용신청 승인 후
python -m fair_value.jobs.trade_batch --mode historical --source all --start-date 2015-01-01
```

실행 전 `.env`에 `FAIR_VALUE_CUSTOMS_API_KEY`와 `FAIR_VALUE_UN_COMTRADE_API_KEY`가 필요합니다.

### Airflow

```bash
docker compose --profile orchestration up -d airflow
```

평일 16:20 KST의 20종목 일봉·1분봉 DAG와 매월 16일 17:30 KST의 UN Comtrade
trade-cycle DAG가 활성 상태입니다. 관세청 수집은 해당 API 활용신청 승인 후
`--source all`로 전환합니다.

## 5차시 과제: 부하·장애·복구 실험

외부 API에는 부하를 주지 않고 저장된 20종목 1분봉을 격리 Kafka topic에 재생했습니다.

| 실험 | 입력/처리 | 결과 | 시간 |
|---|---:|---:|---:|
| 기준 Producer | 7,540 | 전송 7,540 | 0.22초 |
| 기준 Consumer | 7,540 | 수신 7,540 | 0.24초 |
| 기준 Spark | 7,540 | Silver 7,540 / feature 20 | 30.69초 |
| 부하 Producer | 추가 30,160 | 누적 37,700 | 0.24초 |
| 부하 Consumer | 37,700 | 수신 37,700 | 0.34초 |
| 부하 Spark | 37,700 | 중복 30,160 제거 / Silver 7,540 | 32.15초 |
| 잘못된 입력 | 10 | quarantine 10 / 정상 Silver 유지 | 32.32초 |
| 복구 재실행 | 37,710 | Silver 7,540 / feature 20 | 30.99초 |

제출용 전체 보고서는 `5주차_README.md`에 정리했습니다.

안전하게 재현하고 복구한 장애는 다음과 같습니다.

- Spark 컨테이너의 저장 디렉터리 권한 오류를 수정한 뒤 재실행
- `price` 누락 이벤트 10건을 정상 데이터와 분리해 quarantine 저장
- 출력 직전 강제 중단 후 기존 Parquet 보존과 멱등 재실행 확인

복구 전후 검증값은 같았습니다.

```text
silver_rows=7540
silver_unique_keys=7540
feature_rows=20
quarantine_rows=10
```

상세 절차와 명령은 `docs/PIPELINE_RELIABILITY_EXPERIMENT.md`에 기록합니다.
