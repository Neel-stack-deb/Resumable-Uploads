class UploadServiceError(Exception):
    def __init__(self, message: str, code: str = "upload_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class UploadNotFoundError(UploadServiceError):
    def __init__(self) -> None:
        super().__init__("Upload session not found", "not_found")


class UploadExpiredError(UploadServiceError):
    def __init__(self) -> None:
        super().__init__("Upload session has expired", "expired")


class UploadConflictError(UploadServiceError):
    def __init__(self, message: str, current_offset: int | None = None) -> None:
        super().__init__(message, "conflict")
        self.current_offset = current_offset


class UploadValidationError(UploadServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "validation_error")


class UploadStateError(UploadServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "invalid_state")
