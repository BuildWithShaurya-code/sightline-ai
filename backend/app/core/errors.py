"""
SightLine AI - Unified Error Hierarchy & Exception Handlers
Provides standardized, structured error responses across all API endpoints.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("sightline.errors")


class SightLineError(Exception):
    """Base exception for all domain-specific application errors."""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(SightLineError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            error_code="NOT_FOUND",
            message=f"{resource} '{identifier}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": identifier},
        )


class ConflictError(SightLineError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="CONFLICT",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationError(SightLineError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="VALIDATION_FAILED",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class AuthenticationError(SightLineError):
    def __init__(self, message: str = "Authentication required or invalid credentials"):
        super().__init__(
            error_code="UNAUTHENTICATED",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthorizationError(SightLineError):
    def __init__(self, message: str = "Insufficient permissions to perform this action"):
        super().__init__(
            error_code="FORBIDDEN",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class LockedError(SightLineError):
    def __init__(self, message: str = "Resource or action is locked", retry_after_seconds: Optional[int] = None):
        details = {}
        if retry_after_seconds is not None:
            details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            error_code="LOCKED",
            message=message,
            status_code=status.HTTP_423_LOCKED,
            details=details,
        )


class PayloadTooLargeError(SightLineError):
    def __init__(self, message: str, max_bytes: int):
        super().__init__(
            error_code="PAYLOAD_TOO_LARGE",
            message=message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={"max_bytes": max_bytes},
        )


class ServiceUnavailableError(SightLineError):
    def __init__(self, message: str = "Required service or dependency is currently unavailable"):
        super().__init__(
            error_code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def build_error_payload(
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> Dict[str, Any]:
    req_id = getattr(request.state, "request_id", None) if request and hasattr(request, "state") else None
    return {
        "error": error_code,
        "message": message,
        "details": details or {},
        "request_id": req_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def sightline_error_handler(request: Request, exc: SightLineError) -> JSONResponse:
    payload = build_error_payload(
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
        request=request,
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = {}
    for err in exc.errors():
        loc = ".".join(str(l) for l in err.get("loc", []))
        details[loc] = err.get("msg", "Validation error")

    payload = build_error_payload(
        error_code="VALIDATION_ERROR",
        message="Request payload failed schema validation",
        details=details,
        request=request,
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)


async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    payload = build_error_payload(
        error_code=f"HTTP_{exc.status_code}",
        message=exc.detail if isinstance(exc.detail, str) else "HTTP Exception",
        details={},
        request=request,
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception: %s", exc)
    payload = build_error_payload(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred. Please contact the surveillance administrator.",
        details={},
        request=request,
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)
