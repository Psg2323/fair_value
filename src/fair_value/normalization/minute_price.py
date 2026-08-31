from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import polars as pl

FINAL_MINUTE_PRICE_COLUMNS = (
    "ticker",
    "trading_date",
    "timestamp",
    "price",
    "volume",
    "source",
)


@dataclass(frozen=True, slots=True)
class MinutePriceQualityReport:
    input_row_count: int
    null_or_type_invalid_count: int
    duplicate_removed_count: int
    output_row_count: int


def normalize_kis_minute_documents(
    documents: Iterable[Mapping[str, object]],
) -> tuple[pl.DataFrame, MinutePriceQualityReport]:
    """Normalize KIS minute-price Bronze documents to the canonical schema."""
    rows: list[dict[str, object]] = []
    sequence = 0
    for document in documents:
        raw_records = document.get("records")
        if not isinstance(raw_records, list):
            raise ValueError("KIS minute Bronze field 'records' must be a list")
        for raw in raw_records:
            if not isinstance(raw, Mapping):
                raise ValueError("Every KIS minute Bronze record must be an object")
            rows.append(
                {
                    "ticker": document.get("ticker"),
                    "_date": raw.get("stck_bsop_date"),
                    "_time": raw.get("stck_cntg_hour"),
                    "price": raw.get("stck_prpr"),
                    "volume": raw.get("cntg_vol"),
                    "source": document.get("source"),
                    "_collected_at": document.get("collected_at"),
                    "_sequence": sequence,
                }
            )
            sequence += 1
    if not rows:
        raise ValueError("No KIS minute-price Bronze records were found")

    typed = (
        pl.DataFrame(rows)
        .with_columns(
            pl.col("ticker").cast(pl.String, strict=False).str.strip_chars(),
            pl.concat_str(["_date", "_time"])
            .str.strptime(pl.Datetime, "%Y%m%d%H%M%S", strict=False)
            .alias("timestamp"),
            pl.col("price").cast(pl.Int64, strict=False),
            pl.col("volume").cast(pl.Int64, strict=False),
            pl.col("source").cast(pl.String, strict=False).str.strip_chars(),
            pl.col("_collected_at").cast(pl.String, strict=False).fill_null(""),
        )
        .with_columns(pl.col("timestamp").dt.date().alias("trading_date"))
    )
    input_count = typed.height
    valid_expression = (
        pl.col("ticker").is_not_null()
        & (pl.col("ticker").str.len_chars() > 0)
        & pl.col("timestamp").is_not_null()
        & pl.col("price").is_not_null()
        & (pl.col("price") > 0)
        & pl.col("volume").is_not_null()
        & (pl.col("volume") >= 0)
        & pl.col("source").is_not_null()
        & (pl.col("source").str.len_chars() > 0)
    )
    valid = typed.filter(valid_expression)
    invalid_count = input_count - valid.height
    deduplicated = (
        valid.sort(["_collected_at", "_sequence"])
        .unique(subset=["ticker", "timestamp"], keep="last")
        .sort(["ticker", "timestamp"])
    )
    duplicate_count = valid.height - deduplicated.height
    final = deduplicated.select(FINAL_MINUTE_PRICE_COLUMNS)
    return final, MinutePriceQualityReport(
        input_row_count=input_count,
        null_or_type_invalid_count=invalid_count,
        duplicate_removed_count=duplicate_count,
        output_row_count=final.height,
    )
