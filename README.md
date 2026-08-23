# 반도체 Fundamental Fair Value 프로젝트

## 1. 프로젝트 개요

이 프로젝트는 반도체 섹터 기업의 재무 데이터와 산업 사이클을 이용해 **Fundamental Fair Value 범위**를 산정하고, 그 유효성을 과거 데이터로 검증하는 데이터 엔지니어링·분석 프로젝트입니다.

목표 출력은 다음 세 가지 시나리오 값입니다.

- `fair_value_low`: 보수적 가정에 따른 하단 가치
- `fair_value_base`: 기준 가정에 따른 중심 가치
- `fair_value_high`: 우호적 가정에 따른 상단 가치

이 출력과 valuation model은 **아직 구현되지 않은 목표 상태**입니다. 프로젝트는 단기 주가 방향이나 특정 시점의 목표주가를 정답처럼 예측하지 않습니다. 또한 시장가격 자체를 intrinsic value의 정답 또는 학습 label로 취급하지 않습니다. 기업의 내재가치를 독립적으로 추정한 뒤 point-in-time 및 walk-forward 방식으로 미래 성과와 가치 범위의 유효성을 검증하는 것이 핵심입니다.

## 2. 분석 대상

### MVP

- 삼성전자 (`005930`)
- SK하이닉스 (`000660`)

### 향후 확장

- Micron Technology
- TSMC
- NVIDIA 등 해외 반도체 기업

해외 기업 확장은 국내 기업용 데이터 파이프라인과 검증 체계가 안정된 이후 진행합니다.

## 3. 구현 상태

### Implemented

- Python 3.12 기반 패키지와 로컬 설정 구조
- 한국투자증권(KIS) API 인증 및 REST client
- 삼성전자·SK하이닉스 Historical daily price 수집
- 장기간 가격 데이터의 로컬 Bronze JSON 저장
- OpenDART API client
- OpenDART 기업 고유번호 및 연도별 재무제표 raw collector
- OpenDART raw 데이터 수집 및 로컬 Bronze 저장
- 로컬 파일시스템 기반 Bronze/Silver/Gold 경로 추상화

### In Progress

- KIS·OpenDART collector의 일관된 실행 진입점
- OpenDART 수집 흐름의 운영 가능한 파이프라인화
- raw 데이터 계약과 오류 처리 기준 정리

OpenDART는 미구현 상태가 아닙니다. Client와 raw 수집 함수가 구현되어 있고 실제 Bronze 데이터도 존재합니다. 다만 증분 처리, 정규화, 자동화된 테스트, 스케줄링은 아직 완성되지 않았습니다.

### Planned

- Daily incremental batch
- OpenDART 재무제표 정규화 및 point-in-time 적재
- Fundamental feature engineering
- Semiconductor cycle feature 및 regime 연구
- Fair Value model과 `low/base/high` 범위 산정
- Point-in-time backtesting 및 walk-forward validation
- Benchmark model 비교
- 해외 반도체 기업 데이터 소스 확장

## 4. Local-first MVP Architecture

현재 데이터 규모에서는 로컬 실행 환경을 우선합니다. 저장과 처리는 필요한 복잡도만 도입하며, 운영 요구와 데이터 규모가 명확해진 뒤 인프라 확장을 결정합니다.

```text
KIS Historical Price ──┐
                      ├──> Local Bronze (raw, immutable-oriented)
OpenDART Financials ──┘               │
                                      ▼
                         Local Silver (normalized, planned)
                                      │
                                      ▼
                    Local Gold (features / valuation, planned)
                                      │
                                      ▼
                      Point-in-time Backtest (planned)
```

### 데이터 계층

- **Bronze — Implemented:** 외부 API 응답과 수집 메타데이터를 원형에 가깝게 보존합니다.
- **Silver — Planned:** 가격과 재무 데이터를 타입·단위·기간 기준으로 정규화하고 point-in-time 관점에서 결합합니다.
- **Gold — Planned:** 가치평가, 산업 사이클 분석, 검증에 필요한 feature와 모델 출력을 생성합니다.

## 5. Valuation Research Direction

최종 valuation algorithm은 아직 확정되지 않았습니다. 다음 항목은 **Candidate / Research Direction**이며 구현 완료된 모델이 아닙니다.

- Residual Income Model
- Normalized FCFF / DCF
- Relative Valuation
- Semiconductor Cycle Regime Model

각 후보는 데이터 가용성, 회계적 타당성, 안정성, 설명 가능성, point-in-time backtesting 결과를 기준으로 평가합니다. 실증 근거에 따라 일부 모델을 선택하거나 여러 모델의 결과와 불확실성을 조합하여 적정가치 범위를 구성할 예정입니다.

## 6. Validation Direction

검증은 시장가격을 intrinsic value의 label로 두는 방식이 아닙니다. 각 평가 시점에 실제로 이용 가능했던 데이터만 사용하여 다음 지표와 절차를 검토합니다.

- Point-in-time financial data
- Walk-forward validation
- Value-to-Price (`V/P`)
- 이후 12M / 24M / 36M 수익률
- `fair_value_low`–`fair_value_high` 범위의 coverage
- 단순 multiple 등 benchmark model과의 비교
- 시기와 cycle regime에 따른 성능 안정성

구체적인 누출 방지, 재작성 재무제표 처리, 거래일 정렬, 평가 지표는 별도 명세에서 정의합니다.

## 7. Repository Structure

```text
config/                       기업 및 향후 모델 설정
data/
  bronze/                     수집한 raw 데이터
  silver/                     정규화 데이터(계획)
  gold/                       feature 및 모델 출력(계획)
src/fair_value/
  collectors/kis/             KIS 인증·가격 수집
  collectors/opendart/        OpenDART raw 수집
  storage/                    로컬 데이터 계층과 저장소
  cli.py                      CLI 진입점
tests/                        자동화 테스트(아직 생성되지 않음)
```

`data/`와 `.env`는 Git 추적 대상이 아닙니다. API key, 계좌 정보, access token, 실제 수집 데이터는 커밋하지 않습니다.

## 8. Local Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
python -m fair_value version
```

환경 변수는 `FAIR_VALUE_` prefix를 사용합니다. 현재 공개 CLI에는 version 명령만 연결되어 있으며 collector 실행 명령은 아직 정식 인터페이스로 제공되지 않습니다.

품질 검사는 다음 도구를 기준으로 합니다.

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

테스트 디렉터리는 아직 없으므로 `pytest` 기반 unit/integration test 구축은 roadmap에 포함됩니다. 외부 API 테스트는 credential과 live network에 의존하지 않도록 mock 또는 저장된 fixture를 사용해야 합니다.

## 9. Planned Documentation

README는 프로젝트의 목표, 현재 상태, 로컬 실행 방법만 설명합니다. 상세 설계는 다음 문서로 분리할 예정입니다.

- `docs/VALUATION_SPEC.md`: 가치평가 후보, 입력 feature, 가정, 범위 산정 규칙
- `docs/DATA_CONTRACT.md`: Bronze/Silver/Gold schema와 point-in-time 데이터 계약
- `docs/BACKTEST_SPEC.md`: walk-forward 절차, 누출 방지, 지표와 benchmark
- `docs/DECISIONS.md`: 주요 설계 선택, 근거, 대안 및 변경 이력

위 문서들은 현재 roadmap 항목이며 아직 구현 완료된 산출물로 간주하지 않습니다.

## 10. Current Scope Boundaries

MVP는 재현 가능한 로컬 데이터 수집, 재무·산업 feature, 적정가치 범위, point-in-time 검증에 집중합니다. 실시간 시장 처리, 뉴스 분석, 대시보드, 분산 처리, 클라우드 인프라는 현재 핵심 아키텍처와 구현 범위에 포함하지 않습니다. 향후 명확한 요구가 생길 때 별도의 설계 결정으로 검토합니다.
