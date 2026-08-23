from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from fair_value.config_loader import load_accounts
from fair_value.features.fundamentals import derive_fundamental_features
from fair_value.features.share_basis import validate_stock_split_coverage
from fair_value.jobs._corporate_actions import load_stock_splits
from fair_value.normalization.financials import (
    FinancialAccountSpec,
    FinancialQualityReport,
    normalize_opendart_financials,
)
from fair_value.settings import PROJECT_ROOT
from fair_value.storage.parquet import write_parquet_atomic

OPENDART_ROOT = PROJECT_ROOT / "data" / "bronze" / "opendart"
SILVER_PATH = PROJECT_ROOT / "data" / "silver" / "financials" / "canonical.parquet"
FEATURE_PATH = PROJECT_ROOT / "data" / "gold" / "features" / "fundamental_features.parquet"


def load_documents(root: Path) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []

    for path in sorted(root.glob("*/*.json")):
        with path.open("r", encoding="utf-8") as file:
            raw_document: object = json.load(file)

        if not isinstance(raw_document, dict):
            raise ValueError(f"OpenDART Bronze document must be an object: {path}")

        documents.append(cast(dict[str, object], raw_document))

    return documents


def load_account_specs() -> list[FinancialAccountSpec]:
    config = load_accounts()
    return [
        FinancialAccountSpec(
            output_column=output_column,
            statements=tuple(account.statements),
            account_ids=tuple(account.ids),
        )
        for output_column, account in config.accounts.items()
    ]


def print_quality(report: FinancialQualityReport) -> None:
    print(f"input_report_count={report.input_report_count}")
    print(f"output_row_count={report.output_row_count}")
    print(f"missing_core_account_count={report.missing_core_account_count}")
    print(f"missing_share_count={report.missing_share_count}")


def main() -> None:
    financial_documents = load_documents(OPENDART_ROOT / "financial_statements")
    share_documents = load_documents(OPENDART_ROOT / "share_counts")
    dividend_documents = load_documents(OPENDART_ROOT / "dividends")
    financials, report = normalize_opendart_financials(
        financial_documents=financial_documents,
        share_documents=share_documents,
        dividend_documents=dividend_documents,
        account_specs=load_account_specs(),
    )
    stock_splits = load_stock_splits()
    share_count_jumps = validate_stock_split_coverage(financials, stock_splits)
    features = derive_fundamental_features(financials, stock_splits)

    silver_path = write_parquet_atomic(financials, SILVER_PATH)
    feature_path = write_parquet_atomic(features, FEATURE_PATH)

    print_quality(report)
    print(f"financial_schema={financials.schema}")
    print(f"feature_row_count={features.height}")
    print(f"covered_material_share_count_jumps={len(share_count_jumps)}")
    print(f"silver_path={silver_path}")
    print(f"feature_path={feature_path}")


if __name__ == "__main__":
    main()
