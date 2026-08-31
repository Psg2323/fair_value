# 데이터 계약

## 데이터 계층

API 원본 응답과 원천 메타데이터는 `data/bronze/`에 저장합니다. 정규화되고 자료형이 지정된 표준 레코드는 `data/silver/`에 저장합니다. 재사용 가능한 입력과 모델
출력은 `data/gold/`에 저장합니다. 전체 이력 적재와 증분 적재는 동일한 표준 스키마로 저장해야 합니다.

## 표준 데이터셋(Canonical)

| 데이터셋 | 키 | 시간 관련 필드 | 현재 데이터 범위 |
| --- | --- | --- | --- |
| `silver/market_price/canonical.parquet` | ticker, trading_date | trading_date | 61,787행; 20종목, 상장일·2015-01-01 중 늦은 날부터 2026-08-28까지. 005930·000660은 1996년부터 |
| `silver/market_price_minute/canonical.parquet` | ticker, timestamp | trading_date, timestamp | 7,540행; 20종목, 2026-08-28 |
| `silver/trade_flows/canonical.parquet` | source, reporter, flow, hs_code, period_end, available_at | period_end, available_at | 3,105개 빈티지·경제 키 3,078개; UN Comtrade 2015-01~2026-06, 관세청 승인 대기 |
| `silver/financials/canonical.parquet` | ticker, period_end, report_code | period_end, available_at | 86행; 2015-12-31부터 2026-06-30까지 |
| `silver/economic_indicators/canonical.parquet` | source, indicator_id, period_end | period_end, available_at | 10,720행; 원천 제공 범위에 따라 ECOS/KOSIS/FRED 2015년부터 |
| `gold/features/trade_cycle_features.parquet` | source, reporter_code, partner_code, period_end, available_at | period_end, available_at | 516행; 수출입·무역수지·YoY·3개월 momentum |
| `gold/model_inputs/valuation_asof_monthly.parquet` | ticker, valuation_date | valuation_date와 원천별 이용 가능 시점 | 250행 |
| `gold/valuation/benchmark_valuations.parquet` | ticker, valuation_date, model_name | 재무 기간과 이용 가능 시점 | 466행 |
| `gold/valuation/fair_value_range.parquet` | ticker, valuation_date | 재무 기간과 이용 가능 시점 | 188행 |
| `gold/backtest/reports/combined_results.parquet` | model, ticker, valuation_date, horizon | 가치평가일과 미래 평가일 | 2,616행 |
| `gold/research/cycle_rim_v1/sensitivity_ranges.parquet` | variant, ticker, valuation_date | 재무 기간과 이용 가능 시점 | 1,692행 |

시장가격 데이터는 자료형이 지정된 OHLCV, 고유한 `ticker + trading_date`, 유효한

1분봉 canonical은 `ticker, trading_date, timestamp, price, volume, source`만
보존하고 `ticker + timestamp`로 중복 제거합니다. KIS 원천에 없는 분봉 OHLC는 만들지
않습니다.

일별 market-state feature는 VWAP, realized volatility, 장초·장후 수익률과 거래량
집중도, 1분 수익률 극값, volume spike, momentum과 reversal을 포함합니다.
`low <= open/close <= high`, `daily_return`, `adjusted=true`를 충족해야 합니다.
재무 입력은 회계 기간과 공시 이용 가능 시점을 별도로 보존합니다. 주당 가치평가
모델은 `equity_per_price_basis_share`와
`earnings_per_price_basis_share_ttm`을 사용합니다. 이 값은 지배기업 소유주지분과
보통주·우선주 전체 유통주식 수를 기준으로 하며, 삼성전자 보통주 전용 BVPS가 아닙니다.

`config/corporate_actions.yaml`은 가격 단위 변환의 기준 정보입니다. 공시된 주식 수는
변경하지 않습니다. 특성값 계층에서는 적용일 이전의 주식 수에 이후 액면분할 배수를
곱해, 주당 재무정보의 단위를 KIS 사후 수정주가와 일치시킵니다. 인접 기간의 중요한
주식 수 변동에는 반드시 명시적인 기업행위(corporate action)가 연결되어야 합니다.

## 이용 가능 시점 규칙

모델 행에는 평가일까지 관측 가능했던 경제지표 중 가장 최근 경제 기간의 값을 연결할
수 있습니다. 과거 기간에 대한 늦은 정정값이 이용 가능 시점 기준으로 더 최신인 경제
기간을 대체해서는 안 됩니다. OpenDART와 KOSIS에는 README에 설명된 최신 스냅샷
중심의 제약이 남아 있습니다. 두 원천 모두 저장된 `available_at`보다 이전 시점으로
소급 적용할 수 없습니다. FRED 모델 입력은 ALFRED 최초 발표 관측값을 사용합니다.

관세청 historical 응답은 원 발표 빈티지를 제공하지 않으므로 `available_at`을 최초
수집일로 둡니다. UN Comtrade는 `lastReleasedAt`이 있으면 이를 사용하고, 없으면
최초 수집일을 사용합니다. 두 원천 모두 과거 수치가 당시 알려졌다고 가정해 소급하지
않습니다.

`data_quality` 작업은 중복 키, 잘못된 OHLCV·수익률, 미수정 시장가격, 기업행위로 설명되지 않는 주식 수 변동, 잘못된 주당 계산, 시간 순서 위반과 미래
as-of 데이터 사용을 거부합니다. 삼성전자 초기 네 기간의 주식 수 `null`은 경고로
남기며 주당 가치평가에서는 제외합니다.

생성된 데이터셋, Bronze 원본과 인증정보는 로컬 산출물이므로 Git에 커밋하지 않습니다.