from enum import StrEnum
from pathlib import Path

from fair_value.settings import get_settings


class DataLayer(StrEnum):
    """데이터 처리 단계."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


def get_layer_path(layer: DataLayer) -> Path:
    """지정한 데이터 계층의 디렉터리 경로를 반환합니다."""
    return get_settings().data_dir / layer.value


def ensure_data_directories() -> None:
    """필요한 데이터 계층 디렉터리를 생성합니다."""
    for layer in DataLayer:
        get_layer_path(layer).mkdir(parents=True, exist_ok=True)