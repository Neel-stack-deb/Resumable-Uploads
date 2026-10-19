import hashlib
from typing import Any

from fastapi.testclient import TestClient


def create_session(
    client: TestClient,
    filename: str = "test.bin",
    total_size: int = 0,
    content_type: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"filename": filename, "total_size": total_size}
    if content_type is not None:
        payload["content_type"] = content_type
    response = client.post("/uploads", json=payload)
    assert response.status_code == 201
    return response.json()


def patch_chunk(
    client: TestClient,
    upload_id: str,
    offset: int,
    data: bytes,
) -> Any:
    return client.patch(
        f"/uploads/{upload_id}",
        content=data,
        headers={
            "Upload-Offset": str(offset),
            "Content-Type": "application/offset+octet-stream",
        },
    )


def head_offset(client: TestClient, upload_id: str) -> int:
    response = client.head(f"/uploads/{upload_id}")
    assert response.status_code == 200
    return int(response.headers["Upload-Offset"])


def complete_upload(client: TestClient, upload_id: str) -> dict[str, Any]:
    response = client.post(f"/uploads/{upload_id}/complete")
    assert response.status_code == 200
    return response.json()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
