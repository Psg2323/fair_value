from datetime import date

import polars as pl

from fair_value.features.fundamentals import derive_fundamental_features
from fair_value.normalization.financials import (
    FinancialAccountSpec,
    normalize_opendart_financials,
)


def test_normalize_opendart_financials_uses_cumulative_income_and_receipt_date() -> None:
    financial_document = {
        "collected_at": "2026-08-15T00:00:00+00:00",
        "request": {
            "ticker": "005930",
            "business_year": 2026,
            "report_code": "11012",
        },
        "response": {
            "list": [
                {
                    "sj_div": "BS",
                    "account_id": "equity",
                    "thstrm_amount": "1000",
                    "rcept_no": "20260814000001",
                    "currency": "KRW",
                },
                {
                    "sj_div": "IS",
                    "account_id": "profit",
                    "thstrm_amount": "30",
                    "thstrm_add_amount": "50",
                    "rcept_no": "20260814000001",
                    "currency": "KRW",
                },
            ]
        },
    }
    share_document = {
        "collected_at": "2026-08-15T00:00:00+00:00",
        "request": {
            "ticker": "005930",
            "business_year": 2026,
            "report_code": "11012",
        },
        "response": {
            "list": [
                {
                    "se": "\ubcf4\ud1b5\uc8fc",
                    "distb_stock_co": "900",
                    "rcept_no": "20260814000001",
                },
                {
                    "se": "\uc6b0\uc120\uc8fc",
                    "distb_stock_co": "100",
                    "rcept_no": "20260814000001",
                },
                {
                    "se": "\ud569\uacc4",
                    "distb_stock_co": "1,000",
                    "rcept_no": "20260814000001",
                },
            ]
        },
    }
    dividend_document = {
        "collected_at": "2026-08-15T00:00:00+00:00",
        "request": {
            "ticker": "005930",
            "business_year": 2026,
            "report_code": "11012",
        },
        "response": {
            "list": [
                {
                    "se": "\uc8fc\ub2f9 \ud604\uae08\ubc30\ub2f9\uae08(\uc6d0)",
                    "stock_knd": "\ubcf4\ud1b5\uc8fc",
                    "thstrm": "500",
                    "rcept_no": "20260814000001",
                }
            ]
        },
    }
    specs = [
        FinancialAccountSpec("equity_parent", ("BS",), ("equity",)),
        FinancialAccountSpec("net_income_parent_ytd", ("IS",), ("profit",)),
    ]

    frame, report = normalize_opendart_financials(
        [financial_document],
        [share_document],
        [dividend_document],
        specs,
    )
    row = frame.row(0, named=True)

    assert row["period_end"] == date(2026, 6, 30)
    assert row["available_at"] == date(2026, 8, 14)
    assert row["net_income_parent_ytd"] == 50
    assert row["total_shares_outstanding"] == 1000
    assert row["dividend_per_share_common_ytd"] == 500
    assert report.missing_core_account_count == 0


def test_derive_fundamental_features_builds_quarters_and_ttm_without_future_rows() -> None:
    rows = []
    periods = [
        (2024, 1, date(2024, 3, 31), 10.0, 100.0),
        (2024, 2, date(2024, 6, 30), 30.0, 110.0),
        (2024, 3, date(2024, 9, 30), 60.0, 120.0),
        (2024, 4, date(2024, 12, 31), 100.0, 130.0),
        (2025, 1, date(2025, 3, 31), 15.0, 140.0),
    ]
    for year, quarter, period_end, cumulative, equity in periods:
        rows.append(
            {
                "ticker": "TEST",
                "business_year": year,
                "report_quarter": quarter,
                "period_end": period_end,
                "available_at": period_end,
                "equity_parent": equity,
                "inventories": equity,
                "total_shares_outstanding": 10,
                "revenue_ytd": cumulative,
                "operating_income_ytd": cumulative,
                "net_income_parent_ytd": cumulative,
                "operating_cash_flow_ytd": cumulative,
                "capex_ytd": cumulative / 2,
            }
        )

    full = derive_fundamental_features(pl.DataFrame(rows))
    truncated = derive_fundamental_features(pl.DataFrame(rows[:4]))
    q4_full = full.filter(pl.col("period_end") == date(2024, 12, 31)).row(0, named=True)
    q4_truncated = truncated.row(-1, named=True)
    q1_2025 = full.row(-1, named=True)

    assert q4_full["revenue_quarter"] == 40.0
    assert q4_full["revenue_ttm"] == 100.0
    assert q4_full["revenue_ttm"] == q4_truncated["revenue_ttm"]
    assert q1_2025["revenue_ttm"] == 105.0
    assert q1_2025["reported_roe_ttm"] == 105.0 / 120.0
