from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import get_upload_service
from app.core.config import get_settings
from app.schemas.upload_schemas import (
    CompleteUploadResponse,
    CreateUploadRequest,
    CreateUploadResponse,
    ErrorResponse,
    UploadStatusResponse,
)
from app.services.errors import (
    UploadConflictError,
    UploadExpiredError,
    UploadNotFoundError,
    UploadServiceError,
    UploadStateError,
    UploadValidationError,
)
from app.services.upload_service import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])

ACCEPTED_PATCH_CONTENT_TYPES = {
    "application/offset+octet-stream",
    "application/octet-stream",
}


def _error_response(exc: UploadServiceError, status_code: int) -> JSONResponse:
    body = ErrorResponse(detail=exc.message, code=exc.code)
    payload = body.model_dump()
    if isinstance(exc, UploadConflictError) and exc.current_offset is not None:
        payload["upload_offset"] = exc.current_offset
    response = JSONResponse(status_code=status_code, content=payload)
    if isinstance(exc, UploadConflictError) and exc.current_offset is not None:
        response.headers["Upload-Offset"] = str(exc.current_offset)
    return response


def _session_headers(session) -> dict[str, str]:
    return {
        "Upload-Offset": str(session.offset),
        "Upload-Length": str(session.total_size),
        "Upload-Status": session.status,
    }


@router.post("", response_model=CreateUploadResponse, status_code=status.HTTP_201_CREATED)
def create_upload(
    body: CreateUploadRequest,
    service: UploadService = Depends(get_upload_service),
) -> CreateUploadResponse:
    try:
        session = service.create_session(
            body.filename, body.total_size, body.content_type
        )
    except UploadValidationError as exc:
        raise _http_validation(exc)
    settings = get_settings()
    return CreateUploadResponse(
        upload_id=session.id,
        total_size=session.total_size,
        offset=session.offset,
        chunk_size_limit=settings.max_chunk_size,
        status=session.status,
    )


def _http_validation(exc: UploadValidationError) -> None:
    from fastapi import HTTPException

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"message": exc.message, "code": exc.code},
    )


@router.head("/{upload_id}")
def head_upload(
    upload_id: str,
    service: UploadService = Depends(get_upload_service),
) -> Response:
    try:
        session = service.get_status(upload_id)
    except UploadNotFoundError:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    except UploadExpiredError:
        return Response(status_code=status.HTTP_410_GONE)
    return Response(status_code=status.HTTP_200_OK, headers=_session_headers(session))


@router.get("/{upload_id}", response_model=UploadStatusResponse)
def get_upload(
    upload_id: str,
    service: UploadService = Depends(get_upload_service),
) -> UploadStatusResponse | JSONResponse:
    try:
        session = service.get_status(upload_id)
    except UploadNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(detail="Upload session not found", code="not_found").model_dump(),
        )
    except UploadExpiredError:
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content=ErrorResponse(detail="Upload session has expired", code="expired").model_dump(),
        )
    return UploadStatusResponse(
        upload_id=session.id,
        filename=session.filename,
        total_size=session.total_size,
        offset=session.offset,
        status=session.status,
        content_type=session.content_type,
        sha256=session.sha256,
        created_at=session.created_at,
        updated_at=session.updated_at,
        expires_at=session.expires_at,
    )


@router.patch("/{upload_id}")
async def patch_upload(
    upload_id: str,
    request: Request,
    service: UploadService = Depends(get_upload_service),
) -> Response:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and content_type not in ACCEPTED_PATCH_CONTENT_TYPES:
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content=ErrorResponse(
                detail="Unsupported Content-Type for upload chunk",
                code="unsupported_media_type",
            ).model_dump(),
        )

    offset_header = request.headers.get("Upload-Offset")
    if offset_header is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                detail="Upload-Offset header is required",
                code="validation_error",
            ).model_dump(),
        )
    try:
        client_offset = int(offset_header)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                detail="Upload-Offset must be an integer",
                code="validation_error",
            ).model_dump(),
        )

    async def body_iter():
        async for chunk in request.stream():
            yield chunk

    try:
        new_offset = await service.append_chunk(upload_id, client_offset, body_iter())
        session = service.get_status(upload_id)
    except UploadNotFoundError as exc:
        return _error_response(exc, status.HTTP_404_NOT_FOUND)
    except UploadExpiredError as exc:
        return _error_response(exc, status.HTTP_410_GONE)
    except UploadConflictError as exc:
        return _error_response(exc, status.HTTP_409_CONFLICT)
    except UploadValidationError as exc:
        return _error_response(exc, status.HTTP_400_BAD_REQUEST)
    except UploadStateError as exc:
        return _error_response(exc, status.HTTP_409_CONFLICT)

    headers = _session_headers(session)
    headers["Upload-Offset"] = str(new_offset)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@router.post("/{upload_id}/complete", response_model=CompleteUploadResponse)
def complete_upload(
    upload_id: str,
    service: UploadService = Depends(get_upload_service),
) -> CompleteUploadResponse | JSONResponse:
    try:
        file_id, size, digest = service.complete_upload(upload_id)
    except UploadNotFoundError as exc:
        return _error_response(exc, status.HTTP_404_NOT_FOUND)
    except UploadExpiredError as exc:
        return _error_response(exc, status.HTTP_410_GONE)
    except UploadValidationError as exc:
        return _error_response(exc, status.HTTP_400_BAD_REQUEST)
    except UploadStateError as exc:
        return _error_response(exc, status.HTTP_409_CONFLICT)

    return CompleteUploadResponse(file_id=file_id, size=size, sha256=digest)


@router.delete("/{upload_id}")
def cancel_upload(
    upload_id: str,
    service: UploadService = Depends(get_upload_service),
) -> Response:
    try:
        service.cancel_upload(upload_id)
    except UploadNotFoundError as exc:
        return _error_response(exc, status.HTTP_404_NOT_FOUND)
    except UploadStateError as exc:
        return _error_response(exc, status.HTTP_409_CONFLICT)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
