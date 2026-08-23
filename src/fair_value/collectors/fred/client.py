from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import cast

import httpx

from fair_value.settings import Settings, get_settings


class FredAPIError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class FredClient:
    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://api.stlouisfed.org",
            timeout=timeout,
            transport=transport,
        )

    def get_series_metadata(self, series_id: str) -> dict[str, object]:
        payload = self._get_json("/fred/series", {"series_id": series_id})
        raw_series = payload.get("seriess")
        if not isinstance(raw_series, list) or not raw_series:
            raise FredAPIError("FRED series metadata is missing")
        series = raw_series[0]
        if not isinstance(series, dict):
            raise FredAPIError("FRED series metadata is invalid")
        return cast(dict[str, object], series)

    def get_initial_release_observations(
        self,
        series_id: str,
        start_period: str,
        end_period: str,
    ) -> list[dict[str, object]]:
        payload = self._get_json(
            "/fred/series/observations",
            {
                "series_id": series_id,
                "observation_start": start_period,
                "observation_end": end_period,
                "realtime_start": "1776-07-04",
                "realtime_end": "9999-12-31",
                "output_type": 4,
                "sort_order": "asc",
                "limit": 100000,
            },
        )
        raw_rows = payload.get("observations")
        if not isinstance(raw_rows, list):
            raise FredAPIError("FRED observations are missing")
        return [cast(dict[str, object], row) for row in raw_rows if isinstance(row, dict)]

    def _get_json(self, path: str, params: Mapping[str, str | int]) -> dict[str, object]:
        api_key = self.settings.fred_api_key.get_secret_value()
        if not api_key:
            raise FredAPIError("FRED API key is not configured")
        request_params = {"api_key": api_key, "file_type": "json", **params}
        try:
            response = self._client.get(path, params=request_params)
            response.raise_for_status()
            payload: object = response.json()
        except (httpx.HTTPError, ValueError):
            raise FredAPIError("FRED HTTP request failed") from None
        if not isinstance(payload, dict):
            raise FredAPIError("FRED response is not an object")
        if "error_code" in payload:
            raise FredAPIError(
                "FRED returned an API error",
                str(payload.get("error_code", "UNKNOWN")),
            )
        return cast(dict[str, object], payload)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FredClient:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
