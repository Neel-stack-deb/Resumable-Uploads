# Resumable Uploads (FastAPI POC)

Proof of concept for resumable file uploads with durable progress in SQLite, local filesystem storage, failure recovery, and SHA-256 verification.

## Requirements

- Python 3.10+
- See `requirements.txt`

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite path |
| `TEMP_STORAGE_DIR` | In-progress files |
| `COMPLETED_STORAGE_DIR` | Finalized files |
| `MAX_FILE_SIZE` | Upper bound per upload |
| `MAX_CHUNK_SIZE` | Max bytes per `PATCH` body |
| `UPLOAD_EXPIRY_SECONDS` | Session TTL |

Defaults target local development. SQLite and a single disk are not a production storage tier.

## Run the API

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API docs.

## CLI client

Upload with interruption and resume:

```bash
# Terminal 1: server running

# Start upload, stop after 2 chunks
python examples/upload_client.py path\to\file.bin --interrupt-after-chunks 2

# Check server offset (authoritative)
python examples/upload_client.py path\to\file.bin --status

# Resume and finish (verifies SHA-256)
python examples/upload_client.py path\to\file.bin --resume
```

State is stored in `examples/.upload_state.json` (gitignored).

## Cleanup expired sessions

```bash
python -m app.cli.cleanup
```

## Tests

```bash
pytest -v
```

Includes a backend-restart integration test that disposes the app engine and reinitializes against the same database and storage directories.

## API summary

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/uploads` | Create session |
| `HEAD` | `/uploads/{id}` | Offset / length / status headers |
| `GET` | `/uploads/{id}` | JSON status (debug) |
| `PATCH` | `/uploads/{id}` | Upload chunk (`Upload-Offset`, binary body) |
| `POST` | `/uploads/{id}/complete` | Finalize and hash |
| `DELETE` | `/uploads/{id}` | Cancel active upload |

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/WORKFLOW.md](docs/WORKFLOW.md)
- [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md)

## Limitations

- Single-process locking (no distributed concurrency).
- Sequential uploads only.
- Local disk paths; avoid cloud-synced folders for durability tests.
