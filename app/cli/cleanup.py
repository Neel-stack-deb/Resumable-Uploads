"""Remove expired upload sessions and their temporary files."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine, init_db
from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService
from app.storage.local_storage import LocalStorage


def run_cleanup() -> int:
    init_db()
    settings = get_settings()
    storage = LocalStorage(settings)
    db = Session(bind=get_engine())
    try:
        service = UploadService(UploadRepository(db), storage, settings)
        return service.cleanup_expired()
    finally:
        db.close()


def main() -> None:
    removed = run_cleanup()
    print(f"Expired sessions cleaned: {removed}")


if __name__ == "__main__":
    main()
