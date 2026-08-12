# 반도체 기업 가치·시장 데이터 분석 플랫폼

## 1. 프로젝트 목표

**반도체 기업의 재무·실적 데이터를 기반으로 펀더멘털 적정가치를 산출하고, 실제 주가·실시간 거래·뉴스 데이터를 함께 분석하여 기업가치와 시장가격의 괴리 및 현재 시장 상태를 확인할 수 있는 데이터 플랫폼을 구축한다.**

기업의 적정가치는 InvestingPro의 Fair Value에서 사용하는 **다중 가치평가 방식**을 참고하여 DCF, 상대가치 등 여러 가치평가 결과를 종합하는 형태로 구성한다.

실제 시장가격과 기업의 펀더멘털 가치를 분리하여 비교하고, 실시간 거래량·가격 변화와 뉴스 데이터를 통해 현재 시장 상황을 함께 확인하는 것을 목표로 한다.

### 분석 대상
  1차
* 삼성전자
* SK하이닉스

2차
* Micron Technology
* NVIDIA
* TSMC

---

## 2. 사용할 데이터(셋)와 출처

데이터 특성에 따라 **Batch / Micro-Batch / Realtime Streaming** 방식으로 수집한다.

| 데이터       | 출처                        | 수집 방식              | 활용               |
| --------- | ------------------------- | ------------------ | ---------------- |
| 과거 주가     | 한국투자은행 Open API / Market API | Batch              | OHLCV, 수익률, 기술지표 |
| 국내 실시간 체결 | 한국투자은행 WebSocket             | Realtime Streaming | 실시간 가격·거래량 분석    |
| 국내 재무제표   | OpenDART                  | Batch              | 삼성전자·SK하이닉스 가치평가 |
| 해외 재무제표   | SEC EDGAR                 | Batch              | 해외 반도체 기업 가치평가   |
| 국내 뉴스     | 네이버 뉴스 검색 API             | Micro-Batch        | 기업 뉴스 및 감성 분석    |
| 글로벌 뉴스    | GDELT                     | Micro-Batch        | 해외 기업 및 반도체 뉴스   |
| 반도체 산업지표  | FRED                      | Batch              | 반도체 업황 및 사이클 분석  |
| 환율·거시경제   | 한국은행 ECOS                 | Batch              | 환율 및 거시지표        |

### 주요 분석 데이터

**주가**

* OHLCV
* 수익률
* 이동평균
* RSI
* 변동성
* 거래량 변화

**재무**

* 매출
* 영업이익
* 당기순이익
* 영업현금흐름
* CAPEX
* 자산 / 부채 / 자본
* EPS

**파생지표**

* FCF
* ROE / ROIC
* 성장률
* 가치평가 모델별 적정가

**뉴스**

* 관련 기업
* 주요 키워드 및 카테고리
* 긍정 / 중립 / 부정
* 주요 내용 요약

뉴스 분석은 로컬에서 모델을 직접 실행하지 않고 **Gemini API 등 외부 LLM API**를 활용하여 분류·감성 분석·요약 결과만 저장한다.

---

## 3. 수집 → 처리 → 저장 흐름

전체 파이프라인은 **Historical/Batch Pipeline**과 **Realtime Streaming Pipeline**으로 나누어 구성한다.

```text
                 Semiconductor Data Platform


[ Historical / Batch ]

주가 REST API ────┐
OpenDART / SEC ───┤
News API ─────────┼──→ Airflow
FRED / ECOS ──────┘       │
                          ▼
                      S3 Bronze
                   원본 데이터 저장
                          │
                          ▼
                      S3 Silver
                정제 / 표준화 / 통합
                          │
                          ▼
                       S3 Gold
                분석용 데이터 생성
                          │
                  ┌───────┴────────┐
                  ▼                ▼
             Glue / Athena    PostgreSQL
                                   │
                                   ▼
                           Apache Superset


[ Realtime Streaming ]

증권사 WebSocket
        │
        ▼
 Python Producer
        │
        ▼
      Kafka
        │
        ▼
 Streaming Consumer
        │
        ▼
  시간 Window 집계
        │
        ▼
 Realtime Metrics
        │
   ┌────┴────┐
   ▼         ▼
 Redis   PostgreSQL
              │
              ▼
       Apache Superset
```

### Batch Pipeline

과거 주가, 재무제표, 뉴스, 산업지표는 Airflow를 통해 주기적으로 수집한다.

수집된 원본은 S3의 **Bronze → Silver → Gold** 구조로 관리한다.

```text
Bronze
외부 API 원본 데이터

   ↓

Silver
정제 / 타입 변환 / 국가별 데이터 표준화

   ↓

Gold
분석 지표 / 가치평가 / 대시보드용 데이터
```

OpenDART와 SEC처럼 서로 다른 구조의 재무 데이터를 공통 스키마로 변환하여 기업 간 비교가 가능하도록 구성한다.

### Fundamental Value

재무 데이터를 기반으로 기업의 펀더멘털 적정가치를 계산한다.

```text
재무 데이터
    ↓
FCF / EPS / ROIC 등 계산
    ↓
여러 가치평가 모델 적용
    ↓
모델별 적정가 산출
    ↓
Fundamental Fair Value
    ↓
현재 Market Price와 비교
```

하나의 가격을 절대적인 적정가로 제시하기보다는 여러 모델 결과를 바탕으로 **적정가치 범위와 현재가 대비 괴리율**을 제공한다.

### Realtime Streaming

장중 실시간 체결 데이터는 WebSocket을 통해 수집하여 Kafka로 전달한다.

```text
WebSocket
   ↓
Kafka
   ↓
Consumer
   ↓
1초 / 1분 / 5분 Window 집계
   ↓
실시간 가격 / 거래량 / 체결 지표
```

현재 거래량을 과거 동일 시간대 평균 거래량과 비교하여 거래량 급증 등의 시장 변화를 분석한다.

### 뉴스 처리

```text
News API
   ↓
중복 제거 / 기업 매핑
   ↓
LLM API
   ↓
감성 / 카테고리 / 요약
   ↓
S3 / PostgreSQL
```

LLM은 기업 적정가치 계산에는 사용하지 않고 **뉴스 분석 영역에서만 활용**한다.

### 최종 대시보드

Apache Superset을 통해 다음 정보를 제공한다.

* 반도체 기업별 현재 시장가격
* Fundamental Fair Value 및 현재가 대비 괴리율
* 매출·영업이익·FCF·ROIC 등 재무 추이
* 과거 및 최근 주가·거래량
* 실시간 거래량 이상 지표
* 뉴스 감성 및 주요 이슈
* 반도체 기업 간 비교

---

## 4. 사용해보고 싶은 기술 후보

| 영역                 | 기술 후보                   | 목적                            |
| ------------------ | ----------------------- | ----------------------------- |
| 데이터 수집             | Python                  | REST API / WebSocket 수집       |
| Workflow           | Apache Airflow          | Batch Pipeline 스케줄링           |
| Streaming          | Apache Kafka            | 실시간 체결 데이터 처리                 |
| Data Lake          | AWS S3                  | Bronze / Silver / Gold 데이터 저장 |
| Data Catalog / ETL | AWS Glue                | 데이터 카탈로그 및 ETL                |
| Query Engine       | AWS Athena              | S3 데이터 SQL 분석                 |
| Serving DB         | PostgreSQL              | 분석·대시보드용 데이터 제공               |
| Cache              | Redis                   | 실시간 데이터 및 지표 저장               |
| News Analysis      | Gemini API / NLP        | 뉴스 분류·감성 분석·요약                |
| Visualization      | Apache Superset         | 분석 및 Near-Realtime 대시보드       |
| Runtime            | Local / OCI Compute     | 파이프라인 실행 환경                   |
| Environment        | Docker / Docker Compose | 서비스 컨테이너 구성                   |
| Version Control    | Git / GitHub            | 소스 및 프로젝트 관리                  |

---

## 프로젝트 요약

> **반도체 기업의 과거 주가·재무·뉴스·산업 데이터는 Airflow 기반 Batch Pipeline으로 수집하여 S3 Data Lake에서 정제·가공하고, 실시간 체결 데이터는 Kafka 기반 Streaming Pipeline으로 처리한다. 재무 데이터를 기반으로 InvestingPro의 다중 가치평가 방식을 참고한 Fundamental Fair Value를 산출하고, 실제 시장가격·거래량·뉴스 데이터와 비교하여 기업가치와 시장가격의 괴리를 분석하는 플랫폼을 구축한다.**
