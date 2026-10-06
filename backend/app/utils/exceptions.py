class AppError(Exception):
    """Base exception for the application."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} with id '{resource_id}' not found",
            status_code=404,
        )


class TranscriptionError(AppError):
    def __init__(self, message: str = "Transcription failed"):
        super().__init__(message=message, status_code=502)


class AnalysisError(AppError):
    def __init__(self, message: str = "Analysis failed"):
        super().__init__(message=message, status_code=502)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=422)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message=message, status_code=401)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Not authorized"):
        super().__init__(message=message, status_code=403)


class ConflictError(AppError):
    """The request is valid but the resource's current state refuses it (409)."""

    def __init__(self, message: str = "Conflict with the resource's current state"):
        super().__init__(message=message, status_code=409)


class DownloadError(AppError):
    def __init__(self, message: str = "Download failed"):
        super().__init__(message=message, status_code=502)


class EmailDeliveryError(AppError):
    """An outbound email could not be handed to the mail service (502)."""

    def __init__(self, message: str = "Email could not be sent"):
        super().__init__(message=message, status_code=502)
