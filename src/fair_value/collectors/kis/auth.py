import json
from datetime import UTC, datetime, timedelta
from typing import cast

import httpx

from fair_value.settings import Settings, get_settings


class KISAuthenticationError(RuntimeError):
    """KIS 인증 실패."""


class KISAuth:
    """KIS 접근토큰 발급 및 캐시 관리."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.token_path = (
            self.settings.data_dir / ".cache" / f"kis_token_{self.settings.kis_environment}.json"
        )

    def get_access_token(self) -> str:
        """유효한 캐시 토큰을 반환하거나 새 토큰을 발급합니다."""
        cached_token = self._load_cached_token()

        if cached_token is not None:
            return cached_token

        return self._issue_access_token()

    def _load_cached_token(self) -> str | None:
        if not self.token_path.exists():
            return None

        try:
            with self.token_path.open("r", encoding="utf-8") as file:
                raw_data: object = json.load(file)

            if not isinstance(raw_data, dict):
                return None

            token = raw_data.get("access_token")
            expires_at_text = raw_data.get("expires_at")

            if not isinstance(token, str) or not isinstance(expires_at_text, str):
                return None

            expires_at = datetime.fromisoformat(expires_at_text)

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            expiry_buffer = datetime.now(UTC) + timedelta(minutes=5)

            if expiry_buffer < expires_at:
                return token

        except (OSError, ValueError, TypeError):
            return None

        return None

    def _issue_access_token(self) -> str:
        app_key = self.settings.kis_app_key.get_secret_value()
        app_secret = self.settings.kis_app_secret.get_secret_value()

        if not app_key or not app_secret:
            raise KISAuthenticationError("KIS 앱키 또는 앱시크릿이 설정되지 않았습니다.")

        url = f"{self.settings.kis_base_url}/oauth2/tokenP"
        request_body = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecret": app_secret,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    url,
                    json=request_body,
                    headers={"content-type": "application/json"},
                )

            response.raise_for_status()
        except httpx.HTTPError as error:
            raise KISAuthenticationError(f"KIS 토큰 발급 요청에 실패했습니다: {error}") from error

        raw_payload: object = response.json()

        if not isinstance(raw_payload, dict):
            raise KISAuthenticationError("KIS 토큰 응답 형식이 올바르지 않습니다.")

        payload = cast(dict[str, object], raw_payload)
        access_token = payload.get("access_token")

        if not isinstance(access_token, str) or not access_token:
            raise KISAuthenticationError(f"KIS 응답에 접근토큰이 없습니다: {payload}")

        expires_in_raw = payload.get("expires_in", 86400)

        try:
            expires_in = int(str(expires_in_raw))
        except ValueError:
            expires_in = 86400

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._save_token(access_token, expires_at)

        return access_token

    def _save_token(self, access_token: str, expires_at: datetime) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

        token_data = {
            "access_token": access_token,
            "expires_at": expires_at.isoformat(),
        }

        with self.token_path.open("w", encoding="utf-8") as file:
            json.dump(token_data, file, ensure_ascii=False, indent=2)

        self.token_path.chmod(0o600)
