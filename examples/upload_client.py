#!/usr/bin/env python3
"""CLI client for resumable uploads (bounded memory, server-authoritative offset)."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx

DEFAULT_STATE = Path(__file__).resolve().parent / ".upload_state.json"
CHUNK_SIZE = 256 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def save_state(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def server_offset(client: httpx.Client, upload_id: str) -> int:
    response = client.head(f"/uploads/{upload_id}")
    response.raise_for_status()
    return int(response.headers["Upload-Offset"])


def create_session(client: httpx.Client, file_path: Path) -> dict:
    size = file_path.stat().st_size
    response = client.post(
        "/uploads",
        json={"filename": file_path.name, "total_size": size},
    )
    response.raise_for_status()
    return response.json()


def upload_file(
    base_url: str,
    file_path: Path,
    state_path: Path,
    interrupt_after_chunks: int | None,
    resume_upload_id: str | None,
) -> None:
    file_path = file_path.resolve()
    if not file_path.is_file():
        raise SystemExit(f"File not found: {file_path}")

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        if resume_upload_id:
            upload_id = resume_upload_id
            session = client.get(f"/uploads/{upload_id}")
            session.raise_for_status()
        else:
            session_body = create_session(client, file_path)
            upload_id = session_body["upload_id"]
            save_state(
                state_path,
                {
                    "upload_id": upload_id,
                    "path": str(file_path),
                    "total_size": file_path.stat().st_size,
                },
            )

        offset = server_offset(client, upload_id)
        chunks_sent = 0

        with open(file_path, "rb") as f:
            f.seek(offset)
            while offset < file_path.stat().st_size:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                response = client.patch(
                    f"/uploads/{upload_id}",
                    content=chunk,
                    headers={
                        "Upload-Offset": str(offset),
                        "Content-Type": "application/offset+octet-stream",
                    },
                )
                if response.status_code == 409:
                    offset = server_offset(client, upload_id)
                    f.seek(offset)
                    continue
                response.raise_for_status()
                offset = int(response.headers.get("Upload-Offset", offset + len(chunk)))
                chunks_sent += 1
                print(f"Uploaded through byte {offset}")

                if interrupt_after_chunks is not None and chunks_sent >= interrupt_after_chunks:
                    print(
                        f"Simulated interruption after {chunks_sent} chunk(s). "
                        f"Upload ID: {upload_id}"
                    )
                    return

        complete = client.post(f"/uploads/{upload_id}/complete")
        complete.raise_for_status()
        result = complete.json()
        local_digest = sha256_file(file_path)
        if local_digest != result["sha256"]:
            raise SystemExit(
                f"Digest mismatch: local={local_digest} server={result['sha256']}"
            )
        print("Upload complete and verified.")
        print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumable upload CLI")
    parser.add_argument("file", type=Path, help="Local file to upload")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--interrupt-after-chunks",
        type=int,
        default=None,
        help="Exit cleanly after N chunks (resume later)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume using upload_id from state file",
    )
    parser.add_argument("--status", action="store_true", help="Show server offset only")
    args = parser.parse_args()

    if args.status:
        state = load_state(args.state_file)
        with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
            offset = server_offset(client, state["upload_id"])
            print(f"upload_id={state['upload_id']} offset={offset}")
        return

    resume_id = None
    if args.resume:
        resume_id = load_state(args.state_file)["upload_id"]

    upload_file(
        args.base_url,
        args.file,
        args.state_file,
        args.interrupt_after_chunks,
        resume_id,
    )


if __name__ == "__main__":
    main()
