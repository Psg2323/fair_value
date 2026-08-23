# 반도체 Fundamental Fair Value 프로젝트

## 1. 프로젝트 개요

이 프로젝트는 삼성전자와 SK하이닉스의 재무 데이터와 반도체 산업 사이클을 이용해 **Fundamental Fair Value 범위**를 산정하고, point-in-time 및 walk-forward 방식으로 검증하는 로컬 데이터 엔지니어링·분석 프로젝트입니다.

목표 출력은 보수·기준·우호 시나리오의 `fair_value_low`, `fair_value_base`, `fair_value_high`입니다. 현재 `research_v0`가 이 형식의 실험 결과를 생성하지만, backtest로 채택된 최종 모델은 아닙니다. 단기 주가 방향을 예측하거나 시장가격을 intrinsic value의 정답 label로 사용하지 않습니다.

## 2. 분석 대상

- 삼성전자 (`005930`)
- SK하이닉스 (`000660`)

Micron, TSMC, NVIDIA 등 해외 기업은 국내 MVP의 데이터 계약과 검증 체계가 안정된 이후 확장합니다.

## 3. 구현 상태

### Implemented

- Python 3.12 기반 로컬 패키지와 환경 설정
- KIS 인증·REST client와 수정주가 Historical collector
- 삼성전자·SK하이닉스 장기 수정 일봉 수집
- 마지막 거래일 이후 KIS daily incremental batch
- 평일 16:20 KST 원천 갱신 → as-of → valuation → backtest와 재기동 catch-up을 위한 local Airflow orchestration
- KIS Bronze → canonical Silver 가격 정규화
- OpenDART client, 기업 고유번호 collector, historical/incremental 실행 진입점
- 2015년 이후 분기·반기·사업보고서 연결 재무제표 raw collector
- OpenDART 주식 총수·자기주식·유통주식 및 배당 raw collector
- ECOS 기준금리·국고채 3년·원/달러 환율 raw collector와 canonical Silver
- KOSIS 반도체 생산·출하·재고 월별 지수 raw collector와 canonical Silver
- FRED/ALFRED 미국 반도체 산업생산·가동률·생산자물가 최초발표값 collector와 canonical Silver
- 정기보고서 접수일 metadata collector
- OpenDART Bronze → point-in-time Silver financial normalization
- 분기 단독값, TTM, ROE, 영업이익률, 재고 증가율, CAPEX 비율, FCF proxy feature
- 반도체 생산·출하·재고 YoY와 재고/출하 비율 cycle candidate feature
- FRED 산업생산·생산자물가 YoY와 가동률 전년차 cycle candidate feature
- 로컬 Bronze/Silver/Gold 경로
- pytest 기반 자동화 테스트
- 과제용 Kafka Producer/Consumer와 Spark batch adapter
- 월말 거래일 기준 point-in-time as-of model input
- Book Value 및 no-growth Residual Income benchmark
- valuation과 분리된 1M·3M·6M·12M backtest v0
- finite-fade cycle-normalized RIM `research_v0`
- parameter scenario 기반 `fair_value_low/base/high`
- 삼성전자 2018년 50:1 액면분할을 반영한 수정주가 기준 주당 feature
- canonical/as-of fail-fast data quality gate와 Airflow 선행 검증 task
- ticker·연도·horizon 및 비중첩 표본을 분리한 Backtest report v1
- 9개 one-at-a-time RIM sensitivity와 고정 가정 연도별 walk-forward 진단

### In Progress

- OpenDART 정정 전 원공시 version 보존
- `research_v0/v1` 결과 해석과 cycle normalization 가정 재검토

### Planned

- semiconductor cycle regime의 추가 실증 검증
- 삼성전자 사업부별 SOTP
- 해외 기업 확장과 일반화 검증
- Airflow 실행 알림과 장기 운영 모니터링 고도화

## 4. Local-first Core Architecture

```text
KIS Price ──────────────────> Local Bronze ──> Silver market_price
OpenDART Financials ─────────> Local Bronze ──> Silver financials
ECOS/KOSIS/FRED Indicators ──> Local Bronze ──> Silver economic_indicators
                                                       │
                              ┌────────────────────────┴─────────────────────┐
                              ▼                                              ▼
                  Gold fundamental features                       Gold cycle features
                              └────────────────────────┬─────────────────────┘
                                                       ▼
                              Valuation / Backtest (research v0 + diagnostics v1)
```

Airflow는 원천 incremental, canonical/feature 재생성, data quality gate, as-of, valuation, backtest 및 report의 실행 순서와 재시도를 담당하는 local orchestration layer입니다. Kafka와 Spark는 수업 과제 adapter이며 이 core data path에 포함하지 않습니다.

## 5. 데이터 출력

### Market Price Silver

경로: `data/silver/market_price/canonical.parquet`

```text
ticker, trading_date, open, high, low, close,
volume, daily_return, source, adjusted
```

Historical과 incremental batch가 같은 schema와 검증 규칙을 사용합니다. `ticker + trading_date`로 중복을 제거하고 OHLC·null·type을 검증합니다.

### Financial Silver

경로: `data/silver/financials/canonical.parquet`

주요 컬럼은 `period_end`, `available_at`, `receipt_no`, 지배주주 귀속 자기자본·순이익, 매출·영업이익, 재고, 현금, 영업현금흐름, CAPEX, 보통주·우선주·전체 유통주식 수와 배당입니다.

### Fundamental Features

경로: `data/gold/features/fundamental_features.parquet`

누적 보고값에서 분기 단독값과 TTM을 계산합니다. `reported_roe_ttm`, `operating_margin_ttm`, `inventory_growth_yoy`, `capex_to_revenue_ttm`, `fcf_proxy_ttm` 등을 제공합니다. KIS 수정주가와 맞추기 위해 공식 corporate-action 설정으로 `price_basis_total_shares_outstanding`, `equity_per_price_basis_share`, `earnings_per_price_basis_share_ttm`을 생성합니다. `roe_ttm_5y_median_candidate`는 연구용 후보 feature이며 확정 valuation 공식이 아닙니다.

### Economic and Cycle Indicators

경로: `data/silver/economic_indicators/canonical.parquet`

ECOS 일별 기준금리·국고채 3년 수익률·원/달러 환율, KOSIS 월별 반도체
생산·출하·재고지수, FRED 월별 미국 반도체 산업생산·가동률·생산자물가를 같은
long schema로 저장합니다. 주요 컬럼은 `indicator_id`, `period_end`,
`available_at`, `value`, `unit`, `availability_basis`입니다. FRED는
ALFRED 최초발표값과 실제 발표일을 사용합니다.

국내 cycle 후보 feature는
`data/gold/features/semiconductor_cycle_features.parquet`, FRED 기반 글로벌 후보는
`data/gold/features/global_semiconductor_cycle_features.parquet`에 저장합니다.
두 출력 모두 확정 regime 모델이 아니라 fundamental normalization 연구용 입력입니다.

### Valuation and Backtest Outputs

- `data/gold/model_inputs/valuation_asof_monthly.parquet`: 평가일 당시 사용 가능했던 입력
- `data/gold/valuation/benchmark_valuations.parquet`: Book Value와 no-growth RIM
- `data/gold/valuation/fair_value_range.parquet`: `research_v0` low/base/high 범위
- `data/gold/backtest/`: valuation 이후 horizon별 사후 평가
- `data/gold/backtest/reports/`: ticker·연도·horizon·비중첩 report v1
- `data/gold/research/cycle_rim_v1/`: sensitivity 및 고정 가정 walk-forward 진단

## 6. Local Development and Batches

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,course]'
cp .env.example .env
```

Historical Bronze를 canonical 가격 Silver로 재생성합니다.

```bash
python -m fair_value.jobs.market_price_batch --mode historical
```

마지막 거래일 다음부터 최신 완료 거래일까지 KIS incremental batch를 실행합니다.
한국시간 16:10 이전 실행은 당일 미완료 가격을 제외하고 전날까지만 요청합니다.

```bash
python -m fair_value.jobs.market_price_batch --mode incremental
```

Airflow 3.3.1은 평일 16:20 Asia/Seoul에 가격·OpenDART·경제지표 갱신부터 valuation과 backtest까지 순차 실행합니다.

```bash
docker compose --profile orchestration up -d --build airflow
docker exec fair-value-airflow airflow dags list
```

컨테이너는 `restart: unless-stopped`로 구성되어 있습니다. Docker Desktop의
**Start Docker Desktop when you sign in**을 활성화하면 Windows 로그인 후 Airflow도
재기동됩니다. 예약 시각에 PC가 꺼져 있었다면 `catchup=False`가 최신 run 하나만 생성합니다. KIS는 마지막 Silver 거래일 이후 누락분을 보충하고, OpenDART는 최근 2개 사업연도, 경제지표는 source별 lookback을 재수집합니다.

OpenDART 전체 이력을 초기화하거나 최근 자료만 갱신한 뒤 Silver/Gold를 생성합니다.

```bash
python -m fair_value.jobs.opendart_batch --mode historical
python -m fair_value.jobs.opendart_batch --mode incremental
python -m fair_value.jobs.financial_batch
```

ECOS/KOSIS/FRED 경제·반도체 사이클 지표를 수집하고 Silver/Gold를 생성합니다.

```bash
python -m fair_value.jobs.economic_batch --mode historical --start-date 2015-01-01
# 최근 ECOS 7일·KOSIS/FRED 62일을 다시 받아 신규값과 정정을 반영
python -m fair_value.jobs.economic_batch --mode incremental
# API 재호출 없이 기존 Bronze에서 재생성
python -m fair_value.jobs.economic_batch --skip-collect
```

API 재호출 없이 현재 canonical 데이터로 as-of, valuation, backtest를 재생성합니다.

```bash
python -m fair_value.jobs.data_quality --scope canonical
python -m fair_value.jobs.asof_dataset
python -m fair_value.jobs.data_quality --scope asof
python -m fair_value.jobs.benchmark_valuation
python -m fair_value.jobs.cycle_rim_valuation
python -m fair_value.jobs.backtest_v0
python -m fair_value.jobs.cycle_rim_backtest
python -m fair_value.jobs.backtest_report

# 수동 research 진단이며 일일 DAG의 모델 선택 단계가 아님
python -m fair_value.jobs.cycle_rim_research_v1
```

코드 품질 검사는 다음과 같습니다.

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

## 7. Kafka and Spark Course Exercise

Kafka 4.0.2 KRaft broker는 기존 로컬 Kafka와 충돌하지 않도록 `localhost:29092`를 사용합니다.

```bash
docker compose up -d kafka

python -m fair_value.coursework.kafka_producer --limit 1000
python -m fair_value.coursework.kafka_consumer --expected-count 1000
```

실행 결과는 Producer 1,000건 전송, Consumer 1,000건 수신입니다. Topic은 `fair_value.market_price.raw.v1`입니다.

Spark 4.0.4 batch adapter 실행:

```bash
docker compose --profile course run --rm spark   /opt/spark/bin/spark-submit   --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4   --conf spark.jars.ivy=/tmp/.ivy2   src/fair_value/coursework/spark_market_price_batch.py
```

Spark는 Kafka 1,000건을 읽어 type/date normalization, null·OHLC 검증, 중복 제거와 `daily_return` 계산을 수행했습니다. 검증 당시 입력 1,000건, 출력 1,000건, invalid·duplicate 0건이었습니다. 과제 출력은 `data/silver/market_price/course_exercise/`에 저장합니다.

## 8. Valuation and Validation Direction

Primary candidate는 cycle-normalized Residual Income Model이며 Book Value와 no-growth Residual Income을 benchmark로 사용합니다. `research_v0`는 5년 finite fade, point-in-time ROE median, FRED cycle 보정과 parameter scenario를 구현했지만 확정 모델이 아닙니다.

Backtest report v1은 월별 전체 표본과 horizon별 비중첩 표본을 분리해 ticker·연도별로 보고합니다. 비중첩 결과도 V/P–미래수익률 관계가 horizon과 ticker에 따라 불안정하며, `research_v0` range coverage는 약 14~18%입니다. 12M 비중첩 표본은 base variant 기준 14건에 불과합니다.

`research_v1` 진단은 forecast 기간, retention, cycle 조정 폭, ERP를 한 번에 하나씩 바꾼 9개 사전 정의 variant를 비교합니다. 최신 base value 대비 변화는 약 ±5%였지만, 미래수익률로 최적 variant를 선택하지 않습니다. 2021~2026 walk-forward도 모든 가정을 사전에 고정한 evaluation fold입니다. 시장가격은 intrinsic value label이 아니며 현재 결과는 어떤 모델도 채택할 근거가 아닙니다.

## 9. Point-in-Time Caveats

- `period_end`는 경제적 측정 시점, `available_at`은 공시·발표·관측 등 실제 이용 가능 시점입니다.
- OpenDART 전체 재무제표 API는 일부 연도에 정정공시의 최신 snapshot을 반환합니다. 현재 canonical은 정정 접수일 이전에 해당 값을 사용하지 않지만, 정정 전 원공시 값은 아직 보존하지 않습니다.
- 삼성전자 초기 네 보고서는 OpenDART 주식 총수 값이 없어 주당 feature가 null입니다. 미래 주식 수로 역보간하지 않습니다.
- KOSIS 과거 값은 최신 source snapshot입니다. `available_at`은 원천 수정일과 월말+35일 중 늦은 날짜를 사용하지만, 최초 공표·정정 전 값은 아직 보존하지 않습니다.
- FRED는 point-in-time 안전성을 위해 ALFRED 최초발표값만 사용합니다. 가동률 최초발표 이력은 2022년 8월부터 제공되며 그 이전 feature는 null입니다. 후속 개정값을 당시 이용 가능 시점별로 재구성하는 full-vintage 처리는 아직 구현하지 않았습니다.
- 삼성전자 지분에는 우선주가 포함되므로 주당 지표는 보통주 전용 BVPS가 아니라 전체 유통주식 기준 값입니다.
- KIS는 전 기간 수정주가입니다. 삼성전자 2018년 50:1 액면분할 이전 보고 주식 수에는 50배 unit factor를 적용해 `equity_per_price_basis_share`를 만들며, reported-share 값은 audit용으로 보존합니다.

## 10. Repository Structure

```text
config/                         기업·계정 mapping
data/bronze/                    KIS/OpenDART raw
data/silver/                    canonical normalized data
data/gold/features/             derived fundamental features
src/fair_value/collectors/      KIS/OpenDART/ECOS/KOSIS/FRED collectors
src/fair_value/normalization/   canonical transformations
src/fair_value/features/        reusable feature calculations
src/fair_value/datasets/        point-in-time as-of datasets
src/fair_value/valuation/       pure benchmark and research valuation logic
src/fair_value/backtest/        model-independent future evaluation/report
src/fair_value/quality/         canonical 및 as-of fail-fast checks
src/fair_value/jobs/            local batch entrypoints
src/fair_value/coursework/      Kafka/Spark course adapters
airflow/                        local scheduler image and DAGs
docs/                           data/model/backtest decisions and specifications
tests/                          unit tests and small fixtures
```

`.env`, API key, token과 실제 `data/`는 Git에 커밋하지 않습니다.

## 11. Documentation

- `docs/DECISIONS.md`: 현재 architecture/model 결정과 trade-off
- `docs/VALUATION_SPEC.md`: benchmark, `research_v0`, sensitivity 입력·수식·가정·한계
- `docs/DATA_CONTRACT.md`: canonical schema, 기간, availability 규칙
- `docs/BACKTEST_SPEC.md`: point-in-time·future evaluation·모델 선택 기준
