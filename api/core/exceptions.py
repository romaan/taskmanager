from typing import Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel


# ---------- Error response schema ----------

class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
    request_id: Optional[str] = None


def _request_id_from(request: Request) -> Optional[str]:
    # Customize if you use a different header/correlation id source
    return request.headers.get("X-Request-ID")


def _json_error(status: int, code: str, message: str, request: Request, details: Any = None) -> JSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=_request_id_from(request),
    ).model_dump()
    return JSONResponse(status_code=status, content=payload)


# ---------- First-class app exceptions (extensible) ----------

class AppError(Exception):
    """Base error type for app; override status_code, code, message as needed."""
    status_code: int = 400
    code: str = "bad_request"
    message: str = "Bad request"

    def __init__(self, message: Optional[str] = None, *, details: Any = None, code: Optional[str] = None, status: Optional[int] = None):
        self.details = details
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status_code = status
        super().__init__(self.message)


class RateLimitExceeded(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests"


class QueueFullError(AppError):
    status_code = 503
    code = "queue_full"
    message = "Task queue is full. Try again later."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Unauthorized"


# ---------- Registration entrypoint ----------

def register_exception_handlers(app: FastAPI, *, map_validation_to_400: bool = True) -> None:
    """
    Call once after creating the FastAPI app to install global, extensible handlers.
    - map_validation_to_400: if True, convert FastAPI's 422 to 400 (your spec requires 400).
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError):
        return _json_error(exc.status_code, exc.code, exc.message, request, details=exc.details)

    # Convert request body/query/path validation errors
    if map_validation_to_400:
        @app.exception_handler(RequestValidationError)
        async def _handle_validation(request: Request, exc: RequestValidationError):
            # Your spec says: return 400 on errors instead of 422
            return _json_error(400, "validation_error", "Invalid request", request, details=exc.errors())

    @app.exception_handler(StarletteHTTPException)
    async def _handle_starlette_http(request: Request, exc: StarletteHTTPException):
        # Preserve status code, but standardize payload shape
        # Example: raise HTTPException(status_code=401, detail="No token") -> code auto-derived
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(exc.status_code, "http_error")
        message = str(exc.detail) if exc.detail else "HTTP error"
        return _json_error(exc.status_code, code, message, request)

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        # Last-resort handler (don’t leak internals)
        return _json_error(500, "internal_error", "Internal Server Error", request)
