"""
Request logging middleware for observability.
Logs all incoming requests with timing and context.
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """
    Request/response logging middleware.
    
    Adds:
    - Request ID tracking
    - Request timing metrics
    - Structured logging for all requests
    """

    def __init__(
        self,
        app,
        skip_paths: list[str] = None,
        log_body: bool = False,
    ):
        super().__init__(app)
        self.skip_paths = skip_paths or [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/favicon.ico",
        ]
        self.log_body = log_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Skip logging for health checks and static paths
        if any(path.startswith(skip) for skip in self.skip_paths):
            return await call_next(request)

        # Generate or get request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Add request ID to state for access in route handlers
        request.state.request_id = request_id

        # Bind request context to logger
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=path,
            method=request.method,
        )

        # Get client info
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "unknown")

        # Start timing
        start_time = time.time()

        # Log request start
        logger.info(
            "request_started",
            client_ip=client_ip,
            user_agent=user_agent[:100] if user_agent else None,
            query_params=dict(request.query_params) if request.query_params else None,
        )

        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log request completion
            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Add timing headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

            return response

        except Exception as exc:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                "request_failed",
                duration_ms=round(duration_ms, 2),
                error=str(exc),
            )

            raise

        finally:
            # Clear context vars
            structlog.contextvars.unbind_contextvars(
                "request_id", "path", "method"
            )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
            
        return request.client.host if request.client else "unknown"


def get_request_id(request: Request) -> str:
    """Get request ID from request state."""
    return getattr(request.state, "request_id", "unknown")


def configure_structlog():
    """Configure structlog for structured logging."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, settings.log_level.upper(), structlog.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Configure on import if not in testing
if not settings.testing:
    configure_structlog()
