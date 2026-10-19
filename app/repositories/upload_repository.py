from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.upload_session import UploadSession, UploadStatus


class UploadRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, session: UploadSession) -> UploadSession:
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def get_by_id(self, upload_id: str) -> UploadSession | None:
        return self._db.get(UploadSession, upload_id)

    def save(self, session: UploadSession) -> UploadSession:
        session.updated_at = datetime.utcnow()
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        return session

    def update_offset_and_status(
        self,
        session: UploadSession,
        offset: int,
        status: UploadStatus,
    ) -> UploadSession:
        session.offset = offset
        session.status = status.value
        return self.save(session)

    def mark_completed(self, session: UploadSession, sha256: str) -> UploadSession:
        session.sha256 = sha256
        session.status = UploadStatus.COMPLETED.value
        session.offset = session.total_size
        return self.save(session)

    def mark_status(self, session: UploadSession, status: UploadStatus) -> UploadSession:
        session.status = status.value
        return self.save(session)

    def list_expired(self, now: datetime) -> list[UploadSession]:
        stmt = select(UploadSession).where(
            UploadSession.expires_at < now,
            UploadSession.status.in_(
                [UploadStatus.CREATED.value, UploadStatus.UPLOADING.value]
            ),
        )
        return list(self._db.scalars(stmt).all())
