import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import Settings
from app.models.upload_session import UploadSession, UploadStatus
from app.repositories.upload_repository import UploadRepository
from app.services.errors import (
    UploadConflictError,
    UploadExpiredError,
    UploadNotFoundError,
    UploadStateError,
    UploadValidationError,
)
from app.storage.base import StorageBackend

_FILENAME_RE = re.compile(r'^[^\\/:*?"<>|]+$')
_ACTIVE_STATUSES = {UploadStatus.CREATED, UploadStatus.UPLOADING}
_UPLOADABLE_STATUSES = {UploadStatus.CREATED, UploadStatus.UPLOADING}


class UploadService:
    _locks: dict[str, asyncio.Lock] = {}

    def __init__(
        self,
        repository: UploadRepository,
        storage: StorageBackend,
        settings: Settings,
    ) -> None:
        self._repo = repository
        self._storage = storage
        self._settings = settings

    @classmethod
    def _lock_for(cls, upload_id: str) -> asyncio.Lock:
        if upload_id not in cls._locks:
            cls._locks[upload_id] = asyncio.Lock()
        return cls._locks[upload_id]

    def _validate_filename(self, filename: str) -> None:
        if not filename or len(filename) > 512:
            raise UploadValidationError("Invalid filename")
        if ".." in filename or "/" in filename or "\\" in filename:
            raise UploadValidationError("Filename must not contain path separators")
        if not _FILENAME_RE.match(filename):
            raise UploadValidationError("Invalid filename characters")

    def _validate_total_size(self, total_size: int) -> None:
        if total_size < 0:
            raise UploadValidationError("total_size must be non-negative")
        if total_size > self._settings.max_file_size:
            raise UploadValidationError("total_size exceeds maximum allowed file size")

    def create_session(
        self,
        filename: str,
        total_size: int,
        content_type: str | None = None,
    ) -> UploadSession:
        self._validate_filename(filename)
        self._validate_total_size(total_size)
        now = datetime.utcnow()
        upload_id = str(uuid.uuid4())
        storage_key = str(uuid.uuid4())
        self._storage.ensure_temp_file(storage_key)
        session = UploadSession(
            id=upload_id,
            storage_key=storage_key,
            filename=filename,
            content_type=content_type,
            total_size=total_size,
            offset=0,
            status=UploadStatus.CREATED.value,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=self._settings.upload_expiry_seconds),
        )
        return self._repo.create(session)

    def _get_session_or_raise(self, upload_id: str) -> UploadSession:
        session = self._repo.get_by_id(upload_id)
        if session is None:
            raise UploadNotFoundError()
        return session

    def _check_expiry(self, session: UploadSession) -> None:
        if datetime.utcnow() > session.expires_at:
            if session.status in (
                UploadStatus.CREATED.value,
                UploadStatus.UPLOADING.value,
            ):
                session.status = UploadStatus.EXPIRED.value
                self._repo.save(session)
            raise UploadExpiredError()

    def _reconcile_offset(self, session: UploadSession) -> int:
        temp_path = self._storage.temp_path(session.storage_key)
        completed_path = self._storage.completed_path(session.storage_key)
        if completed_path.exists():
            file_len = self._storage.file_size(completed_path)
        else:
            file_len = self._storage.file_size(temp_path)
        file_len = min(file_len, session.total_size)
        db_offset = session.offset
        if file_len > db_offset:
            session.offset = file_len
            if session.status == UploadStatus.CREATED.value and file_len > 0:
                session.status = UploadStatus.UPLOADING.value
            self._repo.save(session)
        elif db_offset > file_len:
            session.offset = file_len
            self._repo.save(session)
        return session.offset

    def get_status(self, upload_id: str) -> UploadSession:
        session = self._get_session_or_raise(upload_id)
        if session.status in (
            UploadStatus.CREATED.value,
            UploadStatus.UPLOADING.value,
        ):
            self._check_expiry(session)
        if session.status in (
            UploadStatus.CREATED.value,
            UploadStatus.UPLOADING.value,
        ):
            self._reconcile_offset(session)
        return session

    async def append_chunk(
        self,
        upload_id: str,
        client_offset: int,
        body_stream: AsyncIterator[bytes],
    ) -> int:
        async with self._lock_for(upload_id):
            session = self._get_session_or_raise(upload_id)
            self._check_expiry(session)
            if session.status not in {s.value for s in _UPLOADABLE_STATUSES}:
                raise UploadStateError(
                    f"Cannot upload in status {session.status}"
                )
            authoritative_offset = self._reconcile_offset(session)

            if client_offset != authoritative_offset:
                raise UploadConflictError(
                    "Upload-Offset does not match server offset",
                    current_offset=authoritative_offset,
                )

            if client_offset > session.total_size:
                raise UploadValidationError("Offset beyond declared file size")

            temp_path = self._storage.temp_path(session.storage_key)
            self._storage.ensure_temp_file(session.storage_key)

            received = 0
            async for chunk in body_stream:
                if not chunk:
                    continue
                received += len(chunk)
                if received > self._settings.max_chunk_size:
                    raise UploadValidationError(
                        "Chunk exceeds maximum allowed request size"
                    )
                if authoritative_offset + received > session.total_size:
                    raise UploadValidationError(
                        "Chunk would exceed declared total file size"
                    )
                await asyncio.to_thread(self._storage.append_stream, temp_path, chunk)

            if received == 0 and session.total_size > 0:
                return authoritative_offset

            new_offset = authoritative_offset + received
            status = (
                UploadStatus.UPLOADING
                if new_offset > 0 or session.total_size == 0
                else UploadStatus.CREATED
            )
            if new_offset > 0:
                status = UploadStatus.UPLOADING
            self._repo.update_offset_and_status(session, new_offset, status)
            return new_offset

    def complete_upload(self, upload_id: str) -> tuple[str, int, str]:
        session = self._get_session_or_raise(upload_id)
        if session.status == UploadStatus.COMPLETED.value:
            if not session.sha256:
                raise UploadStateError("Completed session missing digest")
            return session.storage_key, session.total_size, session.sha256

        if session.status == UploadStatus.CANCELLED.value:
            raise UploadStateError("Upload was cancelled")
        if session.status == UploadStatus.EXPIRED.value:
            raise UploadExpiredError()
        if session.status == UploadStatus.FAILED.value:
            raise UploadStateError("Upload failed")

        self._check_expiry(session)
        authoritative_offset = self._reconcile_offset(session)
        if authoritative_offset != session.total_size:
            raise UploadValidationError("Upload is incomplete")

        temp_path = self._storage.temp_path(session.storage_key)
        if self._storage.file_size(temp_path) != session.total_size:
            raise UploadValidationError("Stored file size does not match expected size")

        completed_path = self._storage.completed_path(session.storage_key)
        if completed_path.exists():
            digest = self._storage.compute_sha256(completed_path)
            self._repo.mark_completed(session, digest)
            return session.storage_key, session.total_size, digest

        self._repo.mark_status(session, UploadStatus.VERIFYING)
        try:
            digest = self._storage.compute_sha256(temp_path)
            self._storage.move_to_completed(session.storage_key)
            self._repo.mark_completed(session, digest)
        except Exception:
            self._repo.mark_status(session, UploadStatus.FAILED)
            raise

        return session.storage_key, session.total_size, digest

    def cancel_upload(self, upload_id: str) -> None:
        session = self._get_session_or_raise(upload_id)
        if session.status == UploadStatus.COMPLETED.value:
            raise UploadStateError("Cannot cancel a completed upload")
        if session.status == UploadStatus.CANCELLED.value:
            return
        self._storage.delete_temp(session.storage_key)
        self._repo.mark_status(session, UploadStatus.CANCELLED)

    def cleanup_expired(self) -> int:
        now = datetime.utcnow()
        expired = self._repo.list_expired(now)
        count = 0
        for session in expired:
            session.status = UploadStatus.EXPIRED.value
            self._storage.delete_temp(session.storage_key)
            self._repo.save(session)
            count += 1
        return count
