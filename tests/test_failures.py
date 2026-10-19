import concurrent.futures

from fastapi.testclient import TestClient

from tests.helpers import create_session, patch_chunk


def test_incorrect_offset_rejected(client: TestClient) -> None:
    upload_id = create_session(client, total_size=100)["upload_id"]
    response = patch_chunk(client, upload_id, 10, b"x" * 10)
    assert response.status_code == 409
    assert response.json()["upload_offset"] == 0


def test_oversized_chunk_rejected(client: TestClient) -> None:
    upload_id = create_session(client, total_size=5000)["upload_id"]
    response = patch_chunk(client, upload_id, 0, b"z" * 2000)
    assert response.status_code == 400


def test_exceeding_declared_size_rejected(client: TestClient) -> None:
    upload_id = create_session(client, total_size=100)["upload_id"]
    response = patch_chunk(client, upload_id, 0, b"a" * 101)
    assert response.status_code == 400


def test_incomplete_finalize_rejected(client: TestClient) -> None:
    upload_id = create_session(client, total_size=200)["upload_id"]
    patch_chunk(client, upload_id, 0, b"a" * 100)
    response = client.post(f"/uploads/{upload_id}/complete")
    assert response.status_code == 400


def test_duplicate_completion_idempotent(client: TestClient) -> None:
    data = b"done" * 50
    upload_id = create_session(client, total_size=len(data))["upload_id"]
    patch_chunk(client, upload_id, 0, data)
    first = client.post(f"/uploads/{upload_id}/complete")
    second = client.post(f"/uploads/{upload_id}/complete")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_cancel_and_cleanup(client: TestClient) -> None:
    upload_id = create_session(client, total_size=100)["upload_id"]
    patch_chunk(client, upload_id, 0, b"abc")
    cancel = client.delete(f"/uploads/{upload_id}")
    assert cancel.status_code == 204
    again = client.delete(f"/uploads/{upload_id}")
    assert again.status_code == 204
    patch = patch_chunk(client, upload_id, 0, b"x")
    assert patch.status_code == 409


def test_ambiguous_retry_requires_head_offset(client: TestClient) -> None:
    data = b"retry-test-data" * 10
    upload_id = create_session(client, total_size=len(data))["upload_id"]
    first = patch_chunk(client, upload_id, 0, data[:80])
    assert first.status_code == 204
    retry = patch_chunk(client, upload_id, 0, data[:80])
    assert retry.status_code == 409
    assert retry.json()["upload_offset"] == 80


def test_concurrent_writes_serialized(client: TestClient) -> None:
    upload_id = create_session(client, total_size=400)["upload_id"]

    def send(offset: int, payload: bytes) -> int:
        return patch_chunk(client, upload_id, offset, payload).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(send, 0, b"a" * 200)
        f2 = pool.submit(send, 0, b"b" * 200)
        codes = {f1.result(), f2.result()}

    assert codes == {204, 409}
