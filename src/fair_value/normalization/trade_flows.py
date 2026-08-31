from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

import polars as pl


@dataclass(frozen=True, slots=True)
class TradeFlowQualityReport:
    input_row_count: int
    invalid_row_count: int
    duplicate_removed_count: int
    output_row_count: int


def normalize_trade_documents(
    documents: Iterable[Mapping[str, object]],
) -> tuple[pl.DataFrame, TradeFlowQualityReport]:
    """Normalize Customs and UN Comtrade Bronze rows without inventing vintages."""
    rows: list[dict[str, object]] = []
    input_count = 0
    for document in documents:
        request = document.get("request")
        response = document.get("response")
        if not isinstance(request, Mapping) or not isinstance(response, Mapping):
            continue
        raw_rows = response.get("rows")
        if not isinstance(raw_rows, list):
            continue
        collected_at = _datetime(document.get("collected_at"))
        source = str(document.get("source", ""))
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                continue
            input_count += 1
            if source == "customs":
                rows.extend(_customs_rows(request, raw, collected_at))
            elif source == "un_comtrade":
                rows.append(_comtrade_row(raw, collected_at))
    if not rows:
        raise ValueError("No Customs or UN Comtrade rows were available")

    frame = pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.col("period_end").cast(pl.Date),
        pl.col("available_at").cast(pl.Date),
        pl.col("trade_value_usd").cast(pl.Float64, strict=False),
        pl.col("net_weight_kg").cast(pl.Float64, strict=False),
        pl.col("quantity").cast(pl.Float64, strict=False),
        pl.col("source_last_released_at").cast(pl.Date, strict=False),
        pl.col("collected_at").cast(pl.Datetime(time_zone="UTC")),
    )
    required = (
        pl.col("period_end").is_not_null()
        & pl.col("available_at").is_not_null()
        & pl.col("source").is_not_null()
        & (pl.col("source").str.len_chars() > 0)
        & pl.col("reporter_code").is_not_null()
        & (pl.col("reporter_code").str.len_chars() > 0)
        & pl.col("partner_code").is_not_null()
        & (pl.col("partner_code").str.len_chars() > 0)
        & pl.col("flow_code").is_in(["X", "M"])
        & pl.col("hs_code").is_not_null()
        & (pl.col("hs_code").str.len_chars() > 0)
        & pl.col("trade_value_usd").is_not_null()
        & (pl.col("trade_value_usd") >= 0)
    )
    valid = frame.filter(required)
    invalid_count = frame.height - valid.height
    keys = [
        "source",
        "reporter_code",
        "partner_code",
        "flow_code",
        "hs_code",
        "period_end",
        "available_at",
    ]
    snapshot_keys = [
        "source",
        "reporter_code",
        "partner_code",
        "flow_code",
        "hs_code",
        "period_end",
    ]
    before = valid.height
    deduplicated = (
        valid.sort([*keys, "collected_at"])
        .unique(subset=keys, keep="last", maintain_order=True)
        .with_columns(
            (pl.col("collected_at") == pl.col("collected_at").max().over(snapshot_keys)).alias(
                "is_latest_source_snapshot"
            )
        )
        .sort([*keys, "collected_at"])
    )
    return deduplicated, TradeFlowQualityReport(
        input_row_count=input_count,
        invalid_row_count=invalid_count,
        duplicate_removed_count=before - deduplicated.height,
        output_row_count=deduplicated.height,
    )


def _customs_rows(
    request: Mapping[str, object],
    raw: Mapping[str, object],
    collected_at: datetime,
) -> list[dict[str, object]]:
    period = raw.get("year") or raw.get("period") or raw.get("yearMonth")
    period_end = _month_end(period)
    hs_code = str(raw.get("hsCode") or request.get("hs_code") or "")
    common = {
        "source": "customs",
        "period": str(period or ""),
        "period_end": period_end,
        "available_at": collected_at.date(),
        "reporter_code": "410",
        "partner_code": "0",
        "hs_code": hs_code,
        "source_last_released_at": None,
        "availability_basis": "first_observed_by_pipeline",
        "is_latest_source_snapshot": True,
        "collected_at": collected_at,
    }
    return [
        {
            **common,
            "flow_code": "X",
            "trade_value_usd": _float(raw.get("expDlr")),
            "net_weight_kg": _float(raw.get("expWgt")),
            "quantity": None,
        },
        {
            **common,
            "flow_code": "M",
            "trade_value_usd": _float(raw.get("impDlr")),
            "net_weight_kg": _float(raw.get("impWgt")),
            "quantity": None,
        },
    ]


def _comtrade_row(
    raw: Mapping[str, object],
    collected_at: datetime,
) -> dict[str, object]:
    period = raw.get("period") or raw.get("refPeriodId")
    released_at = _date(raw.get("lastReleasedAt"))
    return {
        "source": "un_comtrade",
        "period": _string(period),
        "period_end": _month_end(period),
        "available_at": released_at or collected_at.date(),
        "reporter_code": _string(raw.get("reporterCode")),
        "partner_code": _string(raw.get("partnerCode")),
        "flow_code": _string(raw.get("flowCode")),
        "hs_code": _string(raw.get("cmdCode")),
        "trade_value_usd": _float(raw.get("primaryValue")),
        "net_weight_kg": _float(raw.get("netWgt")),
        "quantity": _float(raw.get("qty")),
        "source_last_released_at": released_at,
        "availability_basis": (
            "source_last_released_at" if released_at else "first_observed_by_pipeline"
        ),
        "is_latest_source_snapshot": True,
        "collected_at": collected_at,
    }


def _month_end(value: object) -> date | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) < 6:
        return None
    year, month = int(digits[:4]), int(digits[4:6])
    if not 1 <= month <= 12:
        return None
    return date(year, month, calendar.monthrange(year, month)[1])


def _date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    return parsed


def _string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _float(value: object) -> float | None:
    text = _string(value).replace(",", "").strip()
    if not text or text in {"-", "...", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
