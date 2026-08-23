from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

import polars as pl

REPORT_PERIODS = {
    "11013": ("q1", 1, 3, 31),
    "11012": ("half", 2, 6, 30),
    "11014": ("q3", 3, 9, 30),
    "11011": ("annual", 4, 12, 31),
}


@dataclass(frozen=True, slots=True)
class FinancialAccountSpec:
    output_column: str
    statements: tuple[str, ...]
    account_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FinancialQualityReport:
    input_report_count: int
    output_row_count: int
    missing_core_account_count: int
    missing_share_count: int


def normalize_opendart_financials(
    financial_documents: Iterable[Mapping[str, object]],
    share_documents: Iterable[Mapping[str, object]],
    dividend_documents: Iterable[Mapping[str, object]],
    account_specs: Sequence[FinancialAccountSpec],
) -> tuple[pl.DataFrame, FinancialQualityReport]:
    """Normalize latest collected OpenDART report snapshots into PIT-aware rows."""
    financial_index = _index_documents(financial_documents)
    share_index = _index_documents(share_documents)
    dividend_index = _index_documents(dividend_documents)
    rows: list[dict[str, object]] = []
    missing_core_account_count = 0

    for key, document in sorted(financial_index.items()):
        ticker, business_year, report_code = key
        response_records = _response_records(document)
        if not response_records:
            continue

        report_period, report_quarter, month, day = REPORT_PERIODS[report_code]
        receipt_numbers = [_first_receipt_number(response_records)]
        row: dict[str, object] = {
            "ticker": ticker,
            "business_year": business_year,
            "report_code": report_code,
            "report_period": report_period,
            "report_quarter": report_quarter,
            "period_end": date(business_year, month, day),
            "receipt_no": receipt_numbers[0],
            "currency": _first_string(response_records, "currency"),
            "source": "opendart",
            "is_latest_filing_snapshot": True,
        }

        for account_spec in account_specs:
            row[account_spec.output_column] = _extract_account_amount(
                response_records,
                account_spec,
            )

        if row.get("equity_parent") is None or row.get("net_income_parent_ytd") is None:
            missing_core_account_count += 1

        share_document = share_index.get(key)
        if share_document is not None:
            share_records = _response_records(share_document)
            receipt_numbers.append(_first_receipt_number(share_records))
            row.update(_extract_share_counts(share_records))
        else:
            row.update(_empty_share_counts())

        row["_share_count_reported"] = row.get("total_shares_outstanding") is not None

        dividend_document = dividend_index.get(key)
        if dividend_document is not None:
            dividend_records = _response_records(dividend_document)
            receipt_numbers.append(_first_receipt_number(dividend_records))
            row.update(_extract_dividends(dividend_records))
        else:
            row.update(_empty_dividends())

        valid_receipts = [value for value in receipt_numbers if value]
        row["available_at"] = max(
            (_receipt_date(value) for value in valid_receipts),
            default=None,
        )
        rows.append(row)

    if not rows:
        raise ValueError("No OpenDART financial reports were available to normalize")

    frame = (
        pl.DataFrame(rows)
        .with_columns(
            pl.col("ticker").cast(pl.String),
            pl.col("business_year").cast(pl.Int32),
            pl.col("report_code").cast(pl.String),
            pl.col("report_period").cast(pl.String),
            pl.col("report_quarter").cast(pl.Int8),
            pl.col("period_end").cast(pl.Date),
            pl.col("available_at").cast(pl.Date),
            pl.col("receipt_no").cast(pl.String),
            pl.col("currency").cast(pl.String),
            pl.col("source").cast(pl.String),
            pl.col("is_latest_filing_snapshot").cast(pl.Boolean),
        )
        .sort(["ticker", "period_end", "available_at"])
    )
    share_columns = (
        "common_shares_outstanding",
        "preferred_shares_outstanding",
        "total_shares_outstanding",
    )
    frame = (
        frame.with_columns(
            [
                pl.col(column_name).forward_fill().over("ticker").alias(column_name)
                for column_name in share_columns
            ]
        )
        .with_columns(
            (
                ~pl.col("_share_count_reported") & pl.col("total_shares_outstanding").is_not_null()
            ).alias("share_count_is_carried_forward")
        )
        .drop("_share_count_reported")
    )
    report = FinancialQualityReport(
        input_report_count=len(financial_index),
        output_row_count=frame.height,
        missing_core_account_count=missing_core_account_count,
        missing_share_count=frame.filter(pl.col("total_shares_outstanding").is_null()).height,
    )
    return frame, report


def _index_documents(
    documents: Iterable[Mapping[str, object]],
) -> dict[tuple[str, int, str], Mapping[str, object]]:
    indexed: dict[tuple[str, int, str], Mapping[str, object]] = {}

    for document in documents:
        request = document.get("request")
        if not isinstance(request, Mapping):
            continue

        ticker = request.get("ticker")
        business_year = request.get("business_year")
        report_code = request.get("report_code")

        if not isinstance(ticker, str) or not isinstance(report_code, str):
            continue

        try:
            year = int(str(business_year))
        except ValueError:
            continue

        if report_code not in REPORT_PERIODS:
            continue

        key = (ticker, year, report_code)
        previous = indexed.get(key)
        if previous is None or str(document.get("collected_at", "")) >= str(
            previous.get("collected_at", "")
        ):
            indexed[key] = document

    return indexed


def _response_records(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    response = document.get("response")
    if not isinstance(response, Mapping):
        return []

    raw_records = response.get("list")
    if not isinstance(raw_records, list):
        return []

    return [
        cast(Mapping[str, object], record) for record in raw_records if isinstance(record, Mapping)
    ]


def _extract_account_amount(
    records: Sequence[Mapping[str, object]],
    spec: FinancialAccountSpec,
) -> int | None:
    for statement in spec.statements:
        for account_id in spec.account_ids:
            for record in records:
                if record.get("sj_div") != statement or record.get("account_id") != account_id:
                    continue

                if statement in {"IS", "CIS"}:
                    cumulative = _parse_int(record.get("thstrm_add_amount"))
                    if cumulative is not None:
                        return cumulative

                return _parse_int(record.get("thstrm_amount"))

    return None


def _extract_share_counts(
    records: Sequence[Mapping[str, object]],
) -> dict[str, int | None]:
    by_type = {
        str(record.get("se")): _parse_int(record.get("distb_stock_co")) for record in records
    }
    common = by_type.get("\ubcf4\ud1b5\uc8fc")
    preferred = by_type.get("\uc6b0\uc120\uc8fc")
    total = by_type.get("\ud569\uacc4")

    if total is None and common is not None:
        total = common + (preferred or 0)

    return {
        "common_shares_outstanding": common,
        "preferred_shares_outstanding": preferred,
        "total_shares_outstanding": total,
    }


def _empty_share_counts() -> dict[str, int | None]:
    return {
        "common_shares_outstanding": None,
        "preferred_shares_outstanding": None,
        "total_shares_outstanding": None,
    }


def _extract_dividends(
    records: Sequence[Mapping[str, object]],
) -> dict[str, int | float | None]:
    common_dps: int | None = None
    total_million: int | None = None
    payout_percent: float | None = None

    for record in records:
        label = record.get("se")
        stock_kind = record.get("stock_knd")

        if (
            label == "\uc8fc\ub2f9 \ud604\uae08\ubc30\ub2f9\uae08(\uc6d0)"
            and stock_kind == "\ubcf4\ud1b5\uc8fc"
        ):
            common_dps = _parse_int(record.get("thstrm"))
        elif label == "\ud604\uae08\ubc30\ub2f9\uae08\ucd1d\uc561(\ubc31\ub9cc\uc6d0)":
            total_million = _parse_int(record.get("thstrm"))
        elif label == "(\uc5f0\uacb0)\ud604\uae08\ubc30\ub2f9\uc131\ud5a5(%)":
            payout_percent = _parse_float(record.get("thstrm"))

    return {
        "dividend_per_share_common_ytd": common_dps,
        "cash_dividend_total_krw_ytd": (
            total_million * 1_000_000 if total_million is not None else None
        ),
        "cash_payout_ratio_ytd": (payout_percent / 100.0 if payout_percent is not None else None),
    }


def _empty_dividends() -> dict[str, int | float | None]:
    return {
        "dividend_per_share_common_ytd": None,
        "cash_dividend_total_krw_ytd": None,
        "cash_payout_ratio_ytd": None,
    }


def _first_receipt_number(records: Sequence[Mapping[str, object]]) -> str | None:
    return _first_string(records, "rcept_no")


def _first_string(
    records: Sequence[Mapping[str, object]],
    key: str,
) -> str | None:
    for record in records:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def _receipt_date(receipt_no: str) -> date:
    return datetime.strptime(receipt_no[:8], "%Y%m%d").date()


def _parse_int(value: object) -> int | None:
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"

    try:
        return int(text)
    except ValueError:
        return None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None

    try:
        return float(text)
    except ValueError:
        return None
