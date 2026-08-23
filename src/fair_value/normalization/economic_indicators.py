from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import polars as pl


@dataclass(frozen=True, slots=True)
class EconomicIndicatorQualityReport:
    input_row_count: int
    invalid_value_count: int
    duplicate_removed_count: int
    output_row_count: int


def normalize_economic_indicators(
    documents: Iterable[Mapping[str, object]],
) -> tuple[pl.DataFrame, EconomicIndicatorQualityReport]:
    rows: list[dict[str, object]] = []
    input_count = 0
    for document in documents:
        request, response = document.get("request"), document.get("response")
        if not isinstance(request, Mapping) or not isinstance(response, Mapping):
            continue
        raw_rows = response.get("rows")
        if not isinstance(raw_rows, list):
            continue
        collected_at = _datetime(document.get("collected_at"))
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                continue
            input_count += 1
            source = str(document.get("source", ""))
            if source == "ecos":
                rows.append(_ecos(request, raw, collected_at))
            elif source == "kosis":
                rows.append(_kosis(request, raw, collected_at))
            elif source == "fred":
                rows.append(_fred(request, raw, collected_at))
    if not rows:
        raise ValueError("No ECOS, KOSIS, or FRED rows were available")

    frame = pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.col("period_end").cast(pl.Date),
        pl.col("available_at").cast(pl.Date),
        pl.col("value").cast(pl.Float64),
        pl.col("source_last_changed").cast(pl.Date),
        pl.col("collected_at").cast(pl.Datetime(time_zone="UTC")),
    )
    invalid = (
        pl.col("value").is_null()
        | pl.col("period_end").is_null()
        | pl.col("available_at").is_null()
    )
    invalid_count = frame.filter(invalid).height
    valid = frame.filter(~invalid).sort(["indicator_id", "period_end", "collected_at"])
    before = valid.height
    valid = valid.unique(
        subset=["indicator_id", "period_end"], keep="last", maintain_order=True
    ).sort(["indicator_id", "period_end"])
    return valid, EconomicIndicatorQualityReport(
        input_count, invalid_count, before - valid.height, valid.height
    )


def _ecos(
    request: Mapping[str, object],
    raw: Mapping[str, object],
    collected_at: datetime,
) -> dict[str, object]:
    period, frequency = str(raw.get("TIME", "")), str(request.get("frequency", ""))
    period_end = _period(period, frequency)
    return {
        "indicator_id": str(request.get("indicator_id", "")),
        "source": "ecos",
        "source_series_id": f"{request.get('stat_code', '')}/{request.get('item_code', '')}",
        "frequency": frequency,
        "period": period,
        "period_end": period_end,
        "available_at": period_end,
        "value": _float(raw.get("DATA_VALUE")),
        "unit": str(raw.get("UNIT_NAME") or request.get("configured_unit", "")),
        "source_last_changed": None,
        "availability_basis": "observation_date",
        "is_latest_source_snapshot": True,
        "collected_at": collected_at,
    }


def _kosis(
    request: Mapping[str, object],
    raw: Mapping[str, object],
    collected_at: datetime,
) -> dict[str, object]:
    period, frequency = str(raw.get("PRD_DE", "")), str(request.get("frequency", ""))
    period_end = _period(period, frequency)
    changed = _compact_date(raw.get("LST_CHN_DE"))
    lag_date = period_end + timedelta(days=int(str(request.get("availability_lag_days", 35))))
    available_at = max(x for x in (lag_date, changed) if x is not None)
    series = "/".join(
        str(request.get(key, ""))
        for key in ("org_id", "table_id", "item_code", "region_code", "industry_code")
    )
    return {
        "indicator_id": str(request.get("indicator_id", "")),
        "source": "kosis",
        "source_series_id": series,
        "frequency": frequency,
        "period": period,
        "period_end": period_end,
        "available_at": available_at,
        "value": _float(raw.get("DT")),
        "unit": str(raw.get("UNIT_NM") or request.get("configured_unit", "")),
        "source_last_changed": changed,
        "availability_basis": "max(source_last_changed,period_end_plus_lag)",
        "is_latest_source_snapshot": True,
        "collected_at": collected_at,
    }


def _fred(
    request: Mapping[str, object],
    raw: Mapping[str, object],
    collected_at: datetime,
) -> dict[str, object]:
    period, frequency = str(raw.get("date", "")), str(request.get("frequency", ""))
    observation_date = date.fromisoformat(period)
    period_end = _month_end(observation_date) if frequency == "M" else observation_date
    released_at = date.fromisoformat(str(raw.get("realtime_start", "")))
    return {
        "indicator_id": str(request.get("indicator_id", "")),
        "source": "fred",
        "source_series_id": str(request.get("series_id", "")),
        "frequency": frequency,
        "period": period,
        "period_end": period_end,
        "available_at": released_at,
        "value": _float(raw.get("value")),
        "unit": str(request.get("configured_unit", "")),
        "source_last_changed": released_at,
        "availability_basis": "fred_initial_release_realtime_start",
        "is_latest_source_snapshot": False,
        "collected_at": collected_at,
    }


def _period(value: str, frequency: str) -> date:
    if frequency == "D":
        return datetime.strptime(value, "%Y%m%d").date()
    if frequency == "M":
        year, month = int(value[:4]), int(value[4:6])
        return date(year, month, calendar.monthrange(year, month)[1])
    raise ValueError(f"Unsupported frequency: {frequency}")


def _month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def _compact_date(value: object) -> date | None:
    text = str(value or "").replace(".", "").replace("-", "").strip()
    return datetime.strptime(text, "%Y%m%d").date() if len(text) == 8 else None


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    return parsed


def _float(value: object) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "..."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
