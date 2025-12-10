"""
Rate limiting middleware using Redis.
Implements sliding window rate limiting per IP and per phone number.
"""

import time
from collections.abc import Callable

import structlog
from config import settings
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis sliding window.

    Limits requests by:
    - IP address (general rate limiting)
    - Phone number (for WhatsApp endpoints)
    """

    def __init__(
        self,
        app,
        redis_url: str = None,
        default_limit: int = 100,
        default_window: int = 60,
    ):
        super().__init__(app)
        self.redis_url = redis_url or settings.redis_url
        self.default_limit = default_limit
        self.default_window = default_window
        self._redis: aioredis.Redis | None = None

        # Endpoint-specific rate limits
        self.endpoint_limits = {
            "/api/v1/whatsapp/webhook": {"limit": 60, "window": 60},
            "/api/v1/voice/call": {"limit": 10, "window": 60},
            "/api/v1/calendar/slots": {"limit": 30, "window": 60},
            "/api/v1/calendar/book": {"limit": 10, "window": 60},
        }

        # Paths to skip rate limiting
        self.skip_paths = [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
        ]

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for proxy headers first
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    def _get_rate_limit_config(self, path: str) -> dict:
        """Get rate limit config for path."""
        for endpoint, config in self.endpoint_limits.items():
            if path.startswith(endpoint):
                return config
        return {"limit": self.default_limit, "window": self.default_window}

    async def _check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using sliding window.

        Returns:
            Tuple of (is_allowed, remaining, reset_time)
        """
        try:
            redis = await self._get_redis()

            now = time.time()
            window_start = now - window

            # Use Redis pipeline for atomic operations
            pipe = redis.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current entries
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry
            pipe.expire(key, window)

            results = await pipe.execute()
            current_count = results[1]

            remaining = max(0, limit - current_count - 1)
            reset_time = int(now + window)

            is_allowed = current_count < limit

            return is_allowed, remaining, reset_time

        except Exception as e:
            logger.warning("rate_limit_check_error", error=str(e))
            # Fail open - allow request if Redis is down
            return True, limit, int(time.time() + window)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip rate limiting for certain paths
        if any(path.startswith(skip) for skip in self.skip_paths):
            return await call_next(request)

        # Get rate limit config for this path
        config = self._get_rate_limit_config(path)
        limit = config["limit"]
        window = config["window"]

        # Build rate limit key
        client_ip = self._get_client_ip(request)
        key = f"ratelimit:{path}:{client_ip}"

        # Check rate limit
        is_allowed, remaining, reset_time = await self._check_rate_limit(key, limit, window)

        # Add rate limit headers to response
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
                limit=limit,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests",
                    "retry_after": window,
                },
                headers={**headers, "Retry-After": str(window)},
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        for header, value in headers.items():
            response.headers[header] = value

        return response


class PhoneRateLimiter:
    """
    Dedicated rate limiter for phone-based rate limiting.
    Used in WhatsApp and voice endpoints.
    """

    def __init__(
        self,
        redis_url: str = None,
        default_limit: int = 30,
        default_window: int = 60,
    ):
        self.redis_url = redis_url or settings.redis_url
        self.default_limit = default_limit
        self.default_window = default_window
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def check_limit(
        self,
        phone: str,
        action: str = "message",
        limit: int | None = None,
        window: int | None = None,
    ) -> bool:
        """
        Check if phone number is within rate limits.

        Args:
            phone: Phone number
            action: Action type (message, voice_note, call)
            limit: Override default limit
            window: Override default window

        Returns:
            True if allowed, False if rate limited
        """
        limit = limit or self.default_limit
        window = window or self.default_window

        phone_clean = phone.replace("+", "").replace(" ", "")
        key = f"phone_ratelimit:{action}:{phone_clean}"

        try:
            redis = await self._get_redis()

            now = time.time()
            window_start = now - window

            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window)

            results = await pipe.execute()
            current_count = results[1]

            is_allowed = current_count < limit

            if not is_allowed:
                logger.warning(
                    "phone_rate_limit_exceeded",
                    phone=phone_clean[-4:],  # Log last 4 digits only
                    action=action,
                    count=current_count,
                )

            return is_allowed

        except Exception as e:
            logger.warning("phone_rate_limit_error", error=str(e))
            return True  # Fail open


# Singleton instance for phone-based rate limiting
phone_rate_limiter = PhoneRateLimiter()
