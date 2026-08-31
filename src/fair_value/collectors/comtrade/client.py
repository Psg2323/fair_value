from __future__ import annotations

import time
from collections.abc import Sequence
from types import TracebackType
from typing import cast

import httpx

from fair_value.settings import Settings, get_settings


class ComtradeAPIError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ComtradeClient:
    """Client for authenticated UN Comtrade final monthly data."""

    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        request_interval: float | None = None,
        max_retries: int = 4,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://comtradeapi.un.org",
            timeout=timeout,
            transport=transport,
        )
        self._request_interval = (
            (0.0 if transport is not None else 1.05)
            if request_interval is None
            else request_interval
        )
        self._max_retries = max_retries
        self._last_request_at: float | None = None

    def get_monthly_trade(
        self,
        periods: Sequence[str],
        reporter_code: str,
        partner_code: str,
        hs_codes: Sequence[str],
        flow_codes: Sequence[str],
        max_records: int = 2500,
    ) -> list[dict[str, object]]:
        api_key = self.settings.un_comtrade_api_key.get_secret_value()
        if not api_key:
            raise ComtradeAPIError("UN Comtrade API key is not configured")
        try:
            response = self._get_with_retry(
                api_key,
                periods,
                reporter_code,
                partner_code,
                hs_codes,
                flow_codes,
                max_records,
            )
            payload: object = response.json()
        except (httpx.HTTPError, ValueError):
            raise ComtradeAPIError("UN Comtrade HTTP request failed") from None
        if not isinstance(payload, dict):
            raise ComtradeAPIError("UN Comtrade response is not an object")
        error = payload.get("error")
        if error:
            raise ComtradeAPIError("UN Comtrade returned an API error")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ComtradeAPIError("UN Comtrade response has no data list")
        return [cast(dict[str, object], row) for row in data if isinstance(row, dict)]

    def _get_with_retry(
        self,
        api_key: str,
        periods: Sequence[str],
        reporter_code: str,
        partner_code: str,
        hs_codes: Sequence[str],
        flow_codes: Sequence[str],
        max_records: int,
    ) -> httpx.Response:
        attempt = 0
        while True:
            self._wait_for_rate_limit()
            response = self._client.get(
                "/data/v1/get/C/M/HS",
                headers={"Ocp-Apim-Subscription-Key": api_key},
                params={
                    "period": ",".join(periods),
                    "reporterCode": reporter_code,
                    "partnerCode": partner_code,
                    "cmdCode": ",".join(hs_codes),
                    "flowCode": ",".join(flow_codes),
                    "maxRecords": max_records,
                    "format_output": "JSON",
                    "breakdownMode": "classic",
                    "includeDesc": "true",
                },
            )
            self._last_request_at = time.monotonic()
            retryable = response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt >= self._max_retries:
                response.raise_for_status()
                return response
            time.sleep(max(1.05, 2**attempt))
            attempt += 1

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None or self._request_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._request_interval:
            time.sleep(self._request_interval - elapsed)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ComtradeClient:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
