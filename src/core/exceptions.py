"""Domain and infrastructure base exceptions."""


class AppBaseException(Exception):
    """Base exception for all application-level errors."""

    def __init__(self, message: str, code: str = "INTERNAL_SERVER_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentNotFoundException(AppBaseException):
    """Raised when a requested document does not exist."""

    def __init__(self, document_id: str):
        super().__init__(
            message=f"Document with id '{document_id}' not found.",
            code="DOCUMENT_NOT_FOUND",
        )


class StorageException(AppBaseException):
    """Raised when an object storage (S3/MinIO) operation fails."""

    def __init__(self, message: str):
        super().__init__(message=message, code="STORAGE_ERROR")


class InvalidFileFormatException(AppBaseException):
    """Raised when uploaded file format is not supported or corrupted."""

    def __init__(self, detail: str):
        super().__init__(message=f"Invalid file format: {detail}", code="INVALID_FILE_FORMAT")


class TaskDispatchException(AppBaseException):
    """Raised when publishing a job to the message broker fails."""

    def __init__(self, detail: str):
        super().__init__(message=f"Failed to dispatch background task: {detail}", code="TASK_DISPATCH_ERROR")

