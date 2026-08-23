from types import TracebackType
from typing import cast

import httpx

from fair_value.settings import Settings, get_settings


class OpenDartAPIError(RuntimeError):
    """OpenDART API 호출 실패."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class OpenDartClient:
    """OpenDART 공통 API 클라이언트."""

    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://opendart.fss.or.kr",
            timeout=timeout,
        )

    def get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, object]:
        response = self._get(path, params)
        raw_payload: object = response.json()

        if not isinstance(raw_payload, dict):
            raise OpenDartAPIError("OpenDART 응답 형식이 올바르지 않습니다.")

        payload = cast(dict[str, object], raw_payload)
        status = payload.get("status")

        if status != "000":
            code = str(status) if status is not None else "UNKNOWN"
            message = payload.get("message", "알 수 없는 오류")
            raise OpenDartAPIError(
                f"OpenDART 오류 {code}: {message}",
                code=code,
            )

        return payload

    def get_bytes(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> bytes:
        return self._get(path, params).content

    def _get(
        self,
        path: str,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        api_key = self.settings.opendart_api_key.get_secret_value()

        if not api_key:
            raise OpenDartAPIError("OpenDART 인증키가 설정되지 않았습니다.")

        request_params = dict(params or {})
        request_params["crtfc_key"] = api_key

        try:
            response = self._client.get(path, params=request_params)
            response.raise_for_status()
        except httpx.HTTPError:
            raise OpenDartAPIError("OpenDART HTTP 요청에 실패했습니다.") from None

        return response

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenDartClient":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
