# Upload workflow

## Normal lifecycle

1. **Create** — `POST /uploads` with `filename` and `total_size`. Server creates a DB row (`CREATED`), empty temp file, and returns `upload_id` and `chunk_size_limit`.
2. **Transfer** — Client `HEAD`s (or `GET`s) to read `Upload-Offset`, then `PATCH`es with `Upload-Offset` and a binary body. Server appends to the temp file, fsyncs, then updates `offset` and `UPLOADING`.
3. **Repeat** until `offset == total_size`.
4. **Complete** — `POST /uploads/{id}/complete` verifies size, hashes the file, moves it to completed storage, sets `COMPLETED` and `sha256`.
5. **Cancel** (optional) — `DELETE` marks `CANCELLED` and removes the temp file. Completed objects are not deleted.

## Recovery sequence

1. Client loses connection or process exits mid-upload.
2. On restart, client loads local state only to recover `upload_id`.
3. Client calls `HEAD /uploads/{id}` for authoritative `Upload-Offset`.
4. Client resumes `PATCH` from that offset.
5. If the client retries an old offset after the server already persisted bytes, the server responds `409` with the current offset; the client must not re-send overlapping data.

## Backend restart

SQLite and temp files survive process exit. A new process runs reconciliation on `HEAD`/`GET`/`PATCH`: if the temp file is longer than the stored `offset`, the DB offset is advanced to the file length (capped at `total_size`).
