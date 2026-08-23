from types import TracebackType
from typing import cast

import httpx

from fair_value.collectors.kis.auth import KISAuth
from fair_value.settings import Settings, get_settings


class KISAPIError(RuntimeError):
    """KIS API 호출 실패."""


class KISClient:
    """KIS REST API 공통 클라이언트."""

    def __init__(
        self,
        settings: Settings | None = None,
        auth: KISAuth | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.settings = settings or get_settings()
        self.auth = auth or KISAuth(self.settings)
        self._client = httpx.Client(
            base_url=self.settings.kis_base_url,
            timeout=timeout,
        )

    def get(
        self,
        path: str,
        tr_id: str,
        params: dict[str, str],
    ) -> dict[str, object]:
        access_token = self.auth.get_access_token()

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": self.settings.kis_app_key.get_secret_value(),
            "appsecret": self.settings.kis_app_secret.get_secret_value(),
            "tr_id": tr_id,
            "custtype": "P",
        }

        try:
            response = self._client.get(
                path,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise KISAPIError(f"KIS HTTP 요청 실패: {error}") from error

        raw_payload: object = response.json()

        if not isinstance(raw_payload, dict):
            raise KISAPIError("KIS 응답 형식이 올바르지 않습니다.")

        payload = cast(dict[str, object], raw_payload)
        result_code = payload.get("rt_cd")

        if result_code not in (None, "0"):
            message_code = payload.get("msg_cd", "UNKNOWN")
            message = payload.get("msg1", "알 수 없는 오류")
            raise KISAPIError(f"KIS 오류 {message_code}: {message}")

        return payload

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KISClient":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
