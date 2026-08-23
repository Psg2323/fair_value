from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import cast

import httpx

from fair_value.settings import Settings, get_settings


class EcosAPIError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class EcosClient:
    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://ecos.bok.or.kr", timeout=timeout, transport=transport
        )

    def get_statistics(
        self,
        stat_code: str,
        frequency: str,
        start_period: str,
        end_period: str,
        item_code: str,
        page_size: int = 1000,
    ) -> list[dict[str, object]]:
        api_key = self.settings.ecos_api_key.get_secret_value()
        if not api_key:
            raise EcosAPIError("ECOS API key is not configured")
        rows: list[dict[str, object]] = []
        start_index, total_count = 1, None
        while total_count is None or start_index <= total_count:
            end_index = start_index + page_size - 1
            path = (
                f"/api/StatisticSearch/{api_key}/json/kr/{start_index}/{end_index}/"
                f"{stat_code}/{frequency}/{start_period}/{end_period}/{item_code}"
            )
            payload = self._get_json(path)
            result = payload.get("RESULT")
            if isinstance(result, Mapping):
                code = str(result.get("CODE", "UNKNOWN"))
                if code == "INFO-200":
                    return rows
                raise EcosAPIError("ECOS returned an API error", code)
            block = payload.get("StatisticSearch")
            if not isinstance(block, Mapping):
                raise EcosAPIError("ECOS StatisticSearch payload is missing")
            try:
                total_count = int(str(block.get("list_total_count", "0")))
            except ValueError as error:
                raise EcosAPIError("ECOS total row count is invalid") from error
            raw_rows = block.get("row", [])
            if not isinstance(raw_rows, list):
                raise EcosAPIError("ECOS rows are invalid")
            page = [cast(dict[str, object], row) for row in raw_rows if isinstance(row, dict)]
            rows.extend(page)
            if not page:
                break
            start_index += page_size
        return rows

    def _get_json(self, path: str) -> dict[str, object]:
        try:
            response = self._client.get(path)
            response.raise_for_status()
            payload: object = response.json()
        except (httpx.HTTPError, ValueError):
            raise EcosAPIError("ECOS HTTP request failed") from None
        if not isinstance(payload, dict):
            raise EcosAPIError("ECOS response is not an object")
        return cast(dict[str, object], payload)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EcosClient:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
