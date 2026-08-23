from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import polars as pl

FINAL_MARKET_PRICE_COLUMNS = (
    "ticker",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "daily_return",
    "source",
    "adjusted",
)


@dataclass(frozen=True, slots=True)
class MarketPriceQualityReport:
    input_row_count: int
    null_or_type_invalid_count: int
    ohlc_invalid_count: int
    duplicate_removed_count: int
    output_row_count: int


def normalize_kis_documents(
    documents: Iterable[Mapping[str, object]],
) -> tuple[pl.DataFrame, MarketPriceQualityReport]:
    """Normalize overlapping KIS Bronze documents into one canonical history."""
    rows: list[dict[str, object]] = []
    sequence = 0

    for document in documents:
        raw_records = document.get("records")

        if not isinstance(raw_records, list):
            raise ValueError("KIS Bronze field 'records' must be a list")

        for raw_record in raw_records:
            if not isinstance(raw_record, Mapping):
                raise ValueError("Every KIS Bronze record must be an object")

            rows.append(
                {
                    "ticker": document.get("ticker"),
                    "trading_date": raw_record.get("stck_bsop_date"),
                    "open": raw_record.get("stck_oprc"),
                    "high": raw_record.get("stck_hgpr"),
                    "low": raw_record.get("stck_lwpr"),
                    "close": raw_record.get("stck_clpr"),
                    "volume": raw_record.get("acml_vol"),
                    "source": document.get("source"),
                    "adjusted": document.get("adjusted"),
                    "_collected_at": document.get("collected_at"),
                    "_sequence": sequence,
                }
            )
            sequence += 1

    if not rows:
        raise ValueError("No KIS Bronze records were found")

    typed = pl.DataFrame(rows).with_columns(
        pl.col("ticker").cast(pl.String, strict=False).str.strip_chars(),
        pl.col("trading_date")
        .cast(pl.String, strict=False)
        .str.strptime(pl.Date, "%Y%m%d", strict=False),
        pl.col("open").cast(pl.Int64, strict=False),
        pl.col("high").cast(pl.Int64, strict=False),
        pl.col("low").cast(pl.Int64, strict=False),
        pl.col("close").cast(pl.Int64, strict=False),
        pl.col("volume").cast(pl.Int64, strict=False),
        pl.col("source").cast(pl.String, strict=False).str.strip_chars(),
        pl.col("adjusted").cast(pl.Boolean, strict=False),
        pl.col("_collected_at").cast(pl.String, strict=False).fill_null(""),
    )

    input_row_count = typed.height
    required_columns = [
        "ticker",
        "trading_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
        "adjusted",
    ]
    required_valid = (
        pl.all_horizontal([pl.col(column_name).is_not_null() for column_name in required_columns])
        & (pl.col("ticker").str.len_chars() > 0)
        & (pl.col("source").str.len_chars() > 0)
    )

    non_null = typed.filter(required_valid)
    null_or_type_invalid_count = input_row_count - non_null.height

    ohlc_valid = (
        (pl.col("open") > 0)
        & (pl.col("high") > 0)
        & (pl.col("low") > 0)
        & (pl.col("close") > 0)
        & (pl.col("volume") >= 0)
        & (pl.col("high") >= pl.max_horizontal("open", "low", "close"))
        & (pl.col("low") <= pl.min_horizontal("open", "high", "close"))
    )
    valid = non_null.filter(ohlc_valid)
    ohlc_invalid_count = non_null.height - valid.height

    deduplicated = (
        valid.sort(["_collected_at", "_sequence"])
        .unique(subset=["ticker", "trading_date"], keep="last")
        .sort(["ticker", "trading_date"])
    )
    duplicate_removed_count = valid.height - deduplicated.height

    final = (
        deduplicated.with_columns(
            (
                pl.col("close").cast(pl.Float64)
                / pl.col("close").shift(1).over("ticker").cast(pl.Float64)
                - 1.0
            ).alias("daily_return")
        )
        .select(FINAL_MARKET_PRICE_COLUMNS)
        .sort(["ticker", "trading_date"])
    )

    report = MarketPriceQualityReport(
        input_row_count=input_row_count,
        null_or_type_invalid_count=null_or_type_invalid_count,
        ohlc_invalid_count=ohlc_invalid_count,
        duplicate_removed_count=duplicate_removed_count,
        output_row_count=final.height,
    )
    return final, report
