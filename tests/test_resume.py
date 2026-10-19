from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.models.upload_session import UploadSession
from app.storage.local_storage import LocalStorage
from tests.conftest import reinit_app_same_env
from tests.helpers import (
    complete_upload,
    create_session,
    head_offset,
    patch_chunk,
    sha256_bytes,
)


def test_backend_restart_resume_and_verify(client: TestClient, upload_env: Path) -> None:
    original = b"restart-proof-" + bytes(range(256)) * 4
    upload_id = create_session(client, filename="restart.bin", total_size=len(original))[
        "upload_id"
    ]
    half = len(original) // 2
    patch_chunk(client, upload_id, 0, original[:half])
    assert head_offset(client, upload_id) == half

    client.close()

    restarted = reinit_app_same_env()
    assert head_offset(restarted, upload_id) == half

    patch_chunk(restarted, upload_id, half, original[half:])
    result = complete_upload(restarted, upload_id)
    assert result["sha256"] == sha256_bytes(original)

    settings = get_settings()
    completed = settings.completed_storage_dir / result["file_id"]
    assert completed.read_bytes() == original


def test_reconcile_file_ahead_of_database(client: TestClient) -> None:
    data = b"reconcile-me" * 20
    upload_id = create_session(client, total_size=len(data))["upload_id"]
    patch_chunk(client, upload_id, 0, data[:100])

    with Session(get_engine()) as db:
        row = db.get(UploadSession, upload_id)
        assert row is not None
        storage_key = row.storage_key
        row.offset = 50
        db.commit()

    settings = get_settings()
    storage = LocalStorage(settings)
    assert storage.file_size(storage.temp_path(storage_key)) == 100

    assert head_offset(client, upload_id) == 100

    patch_chunk(client, upload_id, 100, data[100:])
    complete_upload(client, upload_id)
