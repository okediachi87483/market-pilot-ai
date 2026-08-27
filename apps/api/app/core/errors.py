"""Application error hierarchy mapped to the API's error envelope.

See docs/api.md §1: every non-2xx response is
{"error": {"code": ..., "message": ..., "details": {...}}}. Routers and
services raise these instead of constructing HTTPException/JSONResponse
directly, so the shape is enforced in exactly one place — see
app.main's exception handlers.
"""

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class ProviderError(AppError):
    status_code = 503
    code = "provider_error"
