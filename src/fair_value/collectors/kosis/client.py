from __future__ import annotations

from types import TracebackType
from typing import cast

import httpx

from fair_value.settings import Settings, get_settings


class KosisAPIError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KosisClient:
    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://kosis.kr", timeout=timeout, transport=transport
        )

    def get_statistics(
        self,
        org_id: str,
        table_id: str,
        item_code: str,
        region_code: str,
        industry_code: str,
        frequency: str,
        start_period: str,
        end_period: str,
    ) -> list[dict[str, object]]:
        api_key = self.settings.kosis_api_key.get_secret_value()
        if not api_key:
            raise KosisAPIError("KOSIS API key is not configured")
        params = {
            "method": "getList",
            "apiKey": api_key,
            "orgId": org_id,
            "tblId": table_id,
            "objL1": region_code,
            "objL2": industry_code,
            "itmId": item_code,
            "prdSe": frequency,
            "startPrdDe": start_period,
            "endPrdDe": end_period,
            "format": "json",
            "jsonVD": "Y",
        }
        try:
            response = self._client.get("/openapi/Param/statisticsParameterData.do", params=params)
            response.raise_for_status()
            payload: object = response.json()
        except (httpx.HTTPError, ValueError):
            raise KosisAPIError("KOSIS HTTP request failed") from None
        if isinstance(payload, dict):
            raise KosisAPIError("KOSIS returned an API error", str(payload.get("err", "UNKNOWN")))
        if not isinstance(payload, list):
            raise KosisAPIError("KOSIS response is not a list")
        return [cast(dict[str, object], row) for row in payload if isinstance(row, dict)]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> KosisClient:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
