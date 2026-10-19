import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import clear_settings_cache
from app.core.database import init_db, reset_db_engine
from app.main import create_app


@pytest.fixture
def upload_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated database and storage directories per test."""
    data = tmp_path / "data"
    temp = data / "temporary"
    completed = data / "completed"
    temp.mkdir(parents=True)
    completed.mkdir(parents=True)
    db_path = data / "test.db"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("TEMP_STORAGE_DIR", str(temp))
    monkeypatch.setenv("COMPLETED_STORAGE_DIR", str(completed))
    monkeypatch.setenv("MAX_FILE_SIZE", str(50 * 1024 * 1024))
    monkeypatch.setenv("MAX_CHUNK_SIZE", str(1024))
    monkeypatch.setenv("UPLOAD_EXPIRY_SECONDS", "3600")

    clear_settings_cache()
    reset_db_engine()
    init_db()
    return data


@pytest.fixture
def client(upload_env: Path) -> Generator[TestClient, None, None]:
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    reset_db_engine()
    clear_settings_cache()


def reinit_app_same_env() -> TestClient:
    """Simulate backend restart with persisted SQLite and filesystem."""
    reset_db_engine()
    clear_settings_cache()
    init_db()
    return TestClient(create_app())
