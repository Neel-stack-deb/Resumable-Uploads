import hashlib
import os
from pathlib import Path

from app.core.config import Settings
from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, settings: Settings) -> None:
        self._temp_dir = settings.temp_storage_dir
        self._completed_dir = settings.completed_storage_dir

    def temp_path(self, storage_key: str) -> Path:
        return self._temp_dir / storage_key

    def completed_path(self, storage_key: str) -> Path:
        return self._completed_dir / storage_key

    def ensure_temp_file(self, storage_key: str) -> Path:
        path = self.temp_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        return path

    def file_size(self, path: Path) -> int:
        if not path.exists():
            return 0
        return path.stat().st_size

    def append_stream(self, path: Path, data: bytes) -> None:
        with open(path, "ab") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    def move_to_completed(self, storage_key: str) -> Path:
        src = self.temp_path(storage_key)
        dst = self.completed_path(storage_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return dst

    def delete_temp(self, storage_key: str) -> None:
        path = self.temp_path(storage_key)
        if path.exists():
            path.unlink()

    def compute_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
