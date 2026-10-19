from fastapi.testclient import TestClient

from tests.helpers import (
    complete_upload,
    create_session,
    head_offset,
    patch_chunk,
    sha256_bytes,
)


def test_create_session(client: TestClient) -> None:
    body = create_session(client, filename="demo.txt", total_size=100)
    assert body["upload_id"]
    assert body["offset"] == 0
    assert body["total_size"] == 100
    assert body["status"] == "CREATED"
    assert body["chunk_size_limit"] == 1024


def test_multi_chunk_upload_and_finalize(client: TestClient) -> None:
    data = b"a" * 500 + b"b" * 500
    session = create_session(client, total_size=len(data))
    upload_id = session["upload_id"]

    r1 = patch_chunk(client, upload_id, 0, data[:600])
    assert r1.status_code == 204
    assert int(r1.headers["Upload-Offset"]) == 600

    r2 = patch_chunk(client, upload_id, 600, data[600:])
    assert r2.status_code == 204
    assert int(r2.headers["Upload-Offset"]) == 1000

    result = complete_upload(client, upload_id)
    assert result["size"] == 1000
    assert result["sha256"] == sha256_bytes(data)

    status = client.get(f"/uploads/{upload_id}").json()
    assert status["status"] == "COMPLETED"


def test_head_reports_durable_offset(client: TestClient) -> None:
    data = b"x" * 200
    upload_id = create_session(client, total_size=len(data))["upload_id"]
    patch_chunk(client, upload_id, 0, data)
    assert head_offset(client, upload_id) == 200


def test_empty_file_complete(client: TestClient) -> None:
    upload_id = create_session(client, total_size=0)["upload_id"]
    result = complete_upload(client, upload_id)
    assert result["size"] == 0
    assert result["sha256"] == sha256_bytes(b"")
