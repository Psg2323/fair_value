from abc import ABC, abstractmethod
from pathlib import Path

from fair_value.storage.paths import DataLayer


class StorageBackend(ABC):
    """데이터 저장소가 구현해야 하는 공통 인터페이스."""

    @abstractmethod
    def write_json(
        self,
        layer: DataLayer,
        relative_path: str | Path,
        data: object,
    ) -> Path:
        """JSON 데이터를 저장하고 저장 경로를 반환합니다."""
        raise NotImplementedError

    @abstractmethod
    def read_json(
        self,
        layer: DataLayer,
        relative_path: str | Path,
    ) -> object:
        """저장된 JSON 데이터를 읽습니다."""
        raise NotImplementedError