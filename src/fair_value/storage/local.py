import json
from pathlib import Path

from fair_value.storage.base import StorageBackend
from fair_value.storage.paths import DataLayer, get_layer_path


class LocalStorage(StorageBackend):
    """로컬 파일시스템 기반 저장소."""

    def _resolve_path(
        self,
        layer: DataLayer,
        relative_path: str | Path,
    ) -> Path:
        base_path = get_layer_path(layer).resolve()
        target_path = (base_path / relative_path).resolve()

        if not target_path.is_relative_to(base_path):
            raise ValueError("데이터 계층 외부 경로에는 접근할 수 없습니다.")

        return target_path

    def write_json(
        self,
        layer: DataLayer,
        relative_path: str | Path,
        data: object,
    ) -> Path:
        target_path = self._resolve_path(layer, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with target_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        return target_path

    def read_json(
        self,
        layer: DataLayer,
        relative_path: str | Path,
    ) -> object:
        target_path = self._resolve_path(layer, relative_path)

        with target_path.open("r", encoding="utf-8") as file:
            data: object = json.load(file)

        return data
