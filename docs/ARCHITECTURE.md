# Architecture

## Overview

The POC is a layered FastAPI service that accepts offset-based resumable uploads. Progress is durable in SQLite; bytes live on the local filesystem under server-generated keys.

## Components

| Layer | Responsibility |
|-------|----------------|
| `app/api/` | HTTP mapping, headers (`Upload-Offset`, etc.), status codes |
| `app/schemas/` | Pydantic request/response models |
| `app/services/` | Upload lifecycle, validation, reconciliation, locking |
| `app/repositories/` | SQLAlchemy persistence for session metadata |
| `app/storage/` | Filesystem append, move, delete, hashing |
| `app/models/` | ORM entity and status enum |
| `app/core/` | Settings and database engine/session factory |

## Dependency boundaries

- **API** depends on **service** and **schemas** only (via FastAPI `Depends`).
- **Service** depends on **repository**, **storage interface**, and **settings**. It never imports FastAPI types.
- **Repository** reads/writes `UploadSession` rows only; no file I/O.
- **Storage** knows paths under configured directories; no HTTP or authorization.

## Concurrency

Per-upload `asyncio.Lock` instances serialize `PATCH` handling for a given `upload_id` within one worker process. Offset checks happen after reconciling filesystem length with the database.

## Persistence layout

- SQLite: `data/uploads.db` (configurable via `DATABASE_URL`)
- Temp files: `{TEMP_STORAGE_DIR}/{storage_key}`
- Completed files: `{COMPLETED_STORAGE_DIR}/{storage_key}`

`storage_key` is a random UUID distinct from the public `upload_id`. Client filenames are display metadata only.
