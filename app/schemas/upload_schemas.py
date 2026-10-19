from datetime import datetime

from pydantic import BaseModel, Field


class CreateUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)
    total_size: int = Field(..., ge=0)
    content_type: str | None = None


class CreateUploadResponse(BaseModel):
    upload_id: str
    total_size: int
    offset: int
    chunk_size_limit: int
    status: str


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    total_size: int
    offset: int
    status: str
    content_type: str | None = None
    sha256: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class CompleteUploadResponse(BaseModel):
    file_id: str
    size: int
    sha256: str


class ErrorResponse(BaseModel):
    detail: str
    code: str
    upload_offset: int | None = None
