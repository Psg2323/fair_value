import copy
import json
from pathlib import Path
from typing import cast

import polars as pl

from fair_value.normalization.market_price import (
    FINAL_MARKET_PRICE_COLUMNS,
    normalize_kis_documents,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "kis_daily_prices_005930_sample.json"
)


def load_fixture() -> dict[str, object]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
        raw_document: object = json.load(file)

    assert isinstance(raw_document, dict)
    return cast(dict[str, object], raw_document)


def test_normalize_kis_documents_builds_canonical_schema_and_return() -> None:
    frame, report = normalize_kis_documents([load_fixture()])

    assert frame.columns == list(FINAL_MARKET_PRICE_COLUMNS)
    assert report.input_row_count == 12
    assert report.output_row_count == 12
    assert report.null_or_type_invalid_count == 0
    assert report.ohlc_invalid_count == 0
    assert report.duplicate_removed_count == 0
    assert frame.schema["trading_date"] == pl.Date
    assert frame.schema["close"] == pl.Int64
    assert frame.schema["daily_return"] == pl.Float64

    ordered = frame.sort("trading_date")
    first = ordered.row(0, named=True)
    second = ordered.row(1, named=True)

    assert first["daily_return"] is None
    assert second["daily_return"] == (second["close"] / first["close"] - 1.0)


def test_normalize_kis_documents_keeps_latest_overlapping_record() -> None:
    original = load_fixture()
    latest = copy.deepcopy(original)
    latest["collected_at"] = "9999-12-31T00:00:00+00:00"

    records = latest["records"]
    assert isinstance(records, list)
    first_record = records[0]
    assert isinstance(first_record, dict)
    target_date = first_record["stck_bsop_date"]
    first_record["acml_vol"] = "123"

    frame, report = normalize_kis_documents([original, latest])
    selected_volume = (
        frame.filter(pl.col("trading_date").dt.strftime("%Y%m%d") == target_date)
        .select("volume")
        .item()
    )

    assert report.input_row_count == 24
    assert report.duplicate_removed_count == 12
    assert report.output_row_count == 12
    assert selected_volume == 123
