from __future__ import annotations

from types import TracebackType
from urllib.parse import unquote
from xml.etree import ElementTree

import httpx

from fair_value.settings import Settings, get_settings


class CustomsAPIError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class CustomsClient:
    """Client for the Korea Customs Service item-trade Open API."""

    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://apis.data.go.kr",
            timeout=timeout,
            transport=transport,
        )

    def get_item_trade(
        self,
        hs_code: str,
        start_period: str,
        end_period: str,
    ) -> list[dict[str, object]]:
        api_key = unquote(self.settings.customs_api_key.get_secret_value())
        if not api_key:
            raise CustomsAPIError("Customs API key is not configured")
        try:
            response = self._client.get(
                "/1220000/Itemtrade/getItemtradeList",
                params={
                    "serviceKey": api_key,
                    "strtYymm": start_period,
                    "endYymm": end_period,
                    "hsSgn": hs_code,
                },
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
        except (httpx.HTTPError, ElementTree.ParseError):
            raise CustomsAPIError("Customs HTTP request failed") from None

        result_code = _element_text(root, ".//resultCode")
        if result_code and result_code not in {"00", "0"}:
            raise CustomsAPIError("Customs returned an API error", result_code)
        return [{child.tag: child.text for child in item} for item in root.findall(".//item")]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CustomsClient:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _element_text(root: ElementTree.Element, path: str) -> str:
    element = root.find(path)
    return (element.text or "").strip() if element is not None else ""
