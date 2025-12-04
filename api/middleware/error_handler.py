"""
Error handling middleware for FastAPI.
Provides consistent error responses and logging.
"""

import traceback
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware.
    
    Catches unhandled exceptions and returns consistent JSON responses.
    Also logs errors with full context for debugging.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
            
        except Exception as exc:
            # Get request context for logging
            request_id = request.headers.get("X-Request-ID", "unknown")
            path = request.url.path
            method = request.method
            
            # Log the full error
            logger.error(
                "unhandled_exception",
                request_id=request_id,
                path=path,
                method=method,
                error=str(exc),
                error_type=type(exc).__name__,
                traceback=traceback.format_exc() if settings.debug_mode else None,
            )

            # Build error response
            error_detail = {
                "error": "internal_server_error",
                "message": "An unexpected error occurred",
                "request_id": request_id,
            }

            # In debug mode, include more details
            if settings.debug_mode:
                error_detail["debug"] = {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }

            return JSONResponse(
                status_code=500,
                content=error_detail,
            )


class APIError(Exception):
    """Base class for API errors with status codes."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "api_error",
        details: dict = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(APIError):
    """Validation error (400)."""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="validation_error",
            details=details,
        )


class AuthenticationError(APIError):
    """Authentication error (401)."""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="authentication_error",
        )


class AuthorizationError(APIError):
    """Authorization error (403)."""
    
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="authorization_error",
        )


class NotFoundError(APIError):
    """Not found error (404)."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            status_code=404,
            error_code="not_found",
        )


class RateLimitError(APIError):
    """Rate limit error (429)."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(
            message=message,
            status_code=429,
            error_code="rate_limit_exceeded",
            details={"retry_after": retry_after},
        )


class ExternalServiceError(APIError):
    """External service error (502)."""
    
    def __init__(self, service: str, message: str = "External service error"):
        super().__init__(
            message=message,
            status_code=502,
            error_code="external_service_error",
            details={"service": service},
        )
