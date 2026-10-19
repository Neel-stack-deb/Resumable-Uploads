from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    @abstractmethod
    def temp_path(self, storage_key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def completed_path(self, storage_key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def ensure_temp_file(self, storage_key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def file_size(self, path: Path) -> int:
        raise NotImplementedError

    @abstractmethod
    def append_stream(self, path: Path, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    def move_to_completed(self, storage_key: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def delete_temp(self, storage_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def compute_sha256(self, path: Path) -> str:
        raise NotImplementedError
