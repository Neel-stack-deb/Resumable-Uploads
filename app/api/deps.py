from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService
from app.storage.local_storage import LocalStorage


def get_upload_service(db: Session = Depends(get_db)) -> UploadService:
    settings = get_settings()
    storage = LocalStorage(settings)
    repository = UploadRepository(db)
    return UploadService(repository, storage, settings)
