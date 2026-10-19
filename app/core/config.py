from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/uploads.db"
    temp_storage_dir: Path = Path("./data/temporary")
    completed_storage_dir: Path = Path("./data/completed")
    max_file_size: int = 1_073_741_824
    max_chunk_size: int = 5_242_880
    upload_expiry_seconds: int = 86_400

    def ensure_directories(self) -> None:
        self.temp_storage_dir.mkdir(parents=True, exist_ok=True)
        self.completed_storage_dir.mkdir(parents=True, exist_ok=True)
        Path("./data").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


def clear_settings_cache() -> None:
    get_settings.cache_clear()
