from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel
from fastapi.responses import JSONResponse

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    """Consistent response envelope used for every success and error response."""

    status: int
    success: bool
    message: str
    data: Optional[T] = None


# ── Single internal builder (success and error share the same path) ───────────

def _build(*, status: int, success: bool, message: str, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=StandardResponse(
            status=status,
            success=success,
            message=message,
            data=data,
        ).model_dump(mode="json"),
    )


# ── Success helpers ───────────────────────────────────────────────────────────

def ok(message: str = "Success", data: Any = None, status: int = 200) -> JSONResponse:
    """200 OK — general success with optional payload."""
    return _build(status=status, success=True, message=message, data=data)


def created(message: str = "Created successfully", data: Any = None) -> JSONResponse:
    """201 Created — resource was created."""
    return _build(status=201, success=True, message=message, data=data)


def no_content(message: str = "Deleted successfully") -> JSONResponse:
    """200 with empty data — preserves the envelope (204 has no body)."""
    return _build(status=200, success=True, message=message, data=None)


# ── Error helpers ─────────────────────────────────────────────────────────────

def error(message: str = "An error occurred", status: int = 400, data: Any = None) -> JSONResponse:
    """Generic error — same envelope shape as all success responses."""
    return _build(status=status, success=False, message=message, data=data)


def bad_request(message: str = "Bad request", data: Any = None) -> JSONResponse:
    return _build(status=400, success=False, message=message, data=data)


def unauthorized(message: str = "Unauthorized") -> JSONResponse:
    return _build(status=401, success=False, message=message)


def forbidden(message: str = "Forbidden") -> JSONResponse:
    return _build(status=403, success=False, message=message)


def not_found(message: str = "Not found") -> JSONResponse:
    return _build(status=404, success=False, message=message)


def conflict(message: str = "Conflict", data: Any = None) -> JSONResponse:
    return _build(status=409, success=False, message=message, data=data)


def unprocessable(message: str = "Unprocessable entity", data: Any = None) -> JSONResponse:
    return _build(status=422, success=False, message=message, data=data)


def server_error(message: str = "An unexpected error occurred. Please try again later.") -> JSONResponse:
    return _build(status=500, success=False, message=message)
