from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pydantic import SecretStr

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """프로젝트 실행 환경설정."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="FAIR_VALUE_",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = PROJECT_ROOT / "data"

    kis_environment: Literal["live", "paper"] = "paper"
    kis_app_key: SecretStr = SecretStr("")
    kis_app_secret: SecretStr = SecretStr("")
    kis_account_number: SecretStr = SecretStr("")
    kis_account_product_code: str = "01"

    @property
    def kis_base_url(self) -> str:
        """실전 또는 모의투자 REST API 주소를 반환합니다."""
        if self.kis_environment == "live":
            return "https://openapi.koreainvestment.com:9443"

        return "https://openapivts.koreainvestment.com:29443"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """환경설정을 한 번만 생성하여 반환합니다."""
    return Settings()