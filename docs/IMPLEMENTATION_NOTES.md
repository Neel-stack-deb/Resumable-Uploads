# Implementation notes

## Offset-based resumability

Uploads are strictly sequential. Each `PATCH` must declare `Upload-Offset` equal to the server’s reconciled offset. The server appends the request body to the temp file and only then increments `offset` in SQLite.

## Client progress is not authoritative

The local JSON state file in `examples/upload_client.py` stores `upload_id` for convenience. After any failure or timeout, the client must call `HEAD` and continue from `Upload-Offset`.

## Retries and idempotency

- **Complete** and **cancel** are idempotent for terminal states.
- **PATCH** is not blindly append-on-retry: if the client repeats an offset that is behind the server (e.g. after a successful write the client never saw `204`), the server returns `409` with the current offset. The client should `HEAD` and continue without duplicating bytes.
- After an ambiguous timeout, always `HEAD` before sending the next chunk.

## Filesystem and database consistency

Write order per chunk:

1. Append bytes to temp file and `fsync`.
2. Commit `offset` (and status) in SQLite.

If the process crashes after (1) but before (2), reconciliation sets `offset = min(total_size, file_length)` on the next access. If the DB is ahead of the file (abnormal), offset is reduced to the file length.

Completion moves the temp file with `os.replace` into completed storage, then marks `COMPLETED` with digest. If the file already exists in completed storage (retry after move), the service hashes and finalizes the row.

## Crash between write and metadata

Documented behavior: bytes on disk may exist without a matching DB offset until the next reconciliation. Clients that respect `HEAD`/`409` offsets remain correct.

## Guarantees and non-guarantees

**Provides (POC / single worker):**

- Durable progress in SQLite and on disk across restarts.
- Offset validation and chunk/total size limits.
- SHA-256 on complete.
- Per-session write serialization in one process.

**Does not guarantee:**

- Cross-machine or multi-worker consistency without external locking.
- POSIX crash durability on all platforms (e.g. sync policies, cloud-synced folders).
- Parallel or out-of-order chunk uploads.

## Evolution to S3 / MinIO

- Map `storage_key` to object key; `PATCH` becomes `UploadPart` with part number derived from offset ÷ part size or explicit part index.
- Store etags per part in SQLite; complete calls `CompleteMultipartUpload`.
- Reconciliation compares listed parts / object size with DB offset.
- Temp “file” becomes staged parts; digest may use multipart ETag rules or server-side checksum API.
