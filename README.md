# 반도체 Fundamental Fair Value 프로젝트

## 프로젝트 개요

반도체 관련 기업의 재무·시장·반도체 경기 데이터를 결합해 **적정가치 범위**를 산출하고, 계산 결과와 주요 경제지표를 **Apache Superset 대시보드**에서 한눈에 확인할 수 있도록 만드는 프로젝트입니다.

## 분석 대상

분석 대상을 1차부터 3차까지 단계적으로 확대할 예정입니다.

| 단계 | 분류 | 대상 기업 |
|---|---|---|
| 1차(MVP) | 메모리 반도체 | 삼성전자, SK하이닉스 |
| 2차 | 반도체 설계·후공정 | DB하이텍, LX세미콘, 제주반도체, 한미반도체 |
| 3차 | 반도체 소재·부품·장비 | HPSP, 주성엔지니어링, 원익IPS, 한솔케미칼, 솔브레인 |

## 최종 시스템

```text
기업 적정가치 산출 → 경제지표 계산 → Apache Superset 시각화
```

최종 플랫폼에서는 다음 내용을 기업·평가일별로 탐색할 수 있도록 구성합니다.

- 현재 주가와 적정가치 low/base/high 비교
- 가치평가 premium·discount 추이
- ROE, 영업이익률, 재고 증가율, CAPEX와 FCF proxy
- 기준금리, 국고채 금리와 원/달러 환율
- 국내외 반도체 생산·출하·재고·가동률 지표
- 기간별 backtest 성과와 모델 진단 결과

## 현재 진행 상태

### 구현 완료

현재 1차 분석 대상인 삼성전자와 SK하이닉스를 기준으로 구현했습니다.

- 주가·재무·경제·반도체 산업 데이터 수집 및 정제
- 평가 당시 공개된 정보만 사용하는 분석 데이터 생성
- 장부가치와 잔여이익 모델을 이용한 적정가치 범위 산출
- 과거 데이터 기반 모델 검증
- Airflow 배치 자동화와 데이터·코드 품질 검사

### 개발·검토 중

- 적정가치 산출 알고리즘 추가 테스트
- 산정값의 신뢰도 기준 정리와 연구 모델의 안정성·설명력 검증
- OpenDART 정정 전 원공시 버전 보존
- 가치평가 가정과 반도체 cycle normalization 재검토
- 반도체 사이클 강세·약세 신호 지표 생성
- 운영 파이프라인에서 Kafka·Spark 적용 여부 검토
- KIS OHLCV 외 데이터의 배치 처리 과정 보완

### 향후 구현 예정

- Apache Superset용 조회 데이터셋과 대시보드 구축
- 적정가치와 실제 주가 비교 시각화
- 핵심 재무·거시경제·반도체 사이클 지표 시각화
- 추가 cycle regime 검증
- 삼성전자 사업부별 SOTP
- 해외 반도체 기업 확장
- 배치 실행 알림과 운영 모니터링 고도화

## 데이터 흐름 아키텍처

```text
KIS / OpenDART / ECOS / KOSIS / FRED
                    │
                    ▼
             Bronze (원천)
                    │
                    ▼
          Silver (정규화 데이터)
                    │
                    ▼
        Gold (feature / as-of dataset)
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
 Valuation / Backtest   경제·사이클 지표
          └─────────┬─────────┘
                    ▼
       Superset 조회 데이터셋 (예정)
                    │
                    ▼
               Dashboard
```

### 주요 결과물

| 구분 | 경로 | 내용 |
|---|---|---|
| 시장가격 | `data/silver/market_price/canonical.parquet` | 수정주가 OHLCV |
| 재무정보 | `data/silver/financials/canonical.parquet` | point-in-time 재무·주식 수·배당 |
| 경제지표 | `data/silver/economic_indicators/canonical.parquet` | 금리·환율·반도체 산업지표 |
| 재무 feature | `data/gold/features/fundamental_features.parquet` | ROE·마진·재고·CAPEX·FCF proxy |
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

> 현재 진행 중인 핵심 데이터 정제·가치평가 파이프라인과 분리된 수업 과제용 처리 과정입니다.

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
