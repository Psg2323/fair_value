from pathlib import Path

import yaml
from pydantic import BaseModel

from fair_value.settings import PROJECT_ROOT


class CompanyConfig(BaseModel):
    """분석 대상 기업 설정."""

    name_ko: str
    name_en: str
    ticker: str
    exchange: str
    currency: str
    enabled: bool = True


class CompaniesConfig(BaseModel):
    """전체 기업 설정."""

    companies: dict[str, CompanyConfig]


def load_companies(path: Path | None = None) -> CompaniesConfig:
    """YAML 파일에서 기업 설정을 읽고 검증합니다."""
    config_path = path or PROJECT_ROOT / "config" / "companies.yaml"

    with config_path.open("r", encoding="utf-8") as file:
        raw_config: object = yaml.safe_load(file)

    return CompaniesConfig.model_validate(raw_config)