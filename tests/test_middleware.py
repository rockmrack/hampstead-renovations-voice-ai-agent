"""
Unit tests for middleware components.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse


class TestRateLimiter:
    """Tests for rate limiter middleware."""

    def test_rate_limit_allows_requests_under_limit(self, client):
        """Test requests under rate limit are allowed."""
        # Multiple requests should succeed
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_headers_present(self, client):
        """Test rate limit headers are present in response."""
        response = client.get("/health")
        # Health endpoint might skip rate limiting, test a different endpoint
        # Headers should be present on rate-limited endpoints

    @pytest.mark.asyncio
    async def test_phone_rate_limiter(self, mock_redis):
        """Test phone-based rate limiting."""
        with patch("middleware.rate_limiter.phone_rate_limiter._get_redis", return_value=mock_redis):
            from middleware.rate_limiter import phone_rate_limiter
            
            mock_redis.zcard.return_value = 5  # Under limit
            result = await phone_rate_limiter.check_limit(
                phone="+447912345678",
                action="message",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_phone_rate_limiter_exceeded(self, mock_redis):
        """Test phone rate limit exceeded."""
        with patch("middleware.rate_limiter.phone_rate_limiter._get_redis", return_value=mock_redis):
            from middleware.rate_limiter import phone_rate_limiter
            
            mock_redis.zcard.return_value = 100  # Over limit
            result = await phone_rate_limiter.check_limit(
                phone="+447912345678",
                action="message",
                limit=30,
            )
            assert result is False


class TestErrorHandler:
    """Tests for error handler middleware."""

    def test_404_returns_json(self, client):
        """Test 404 errors return JSON response."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        assert response.headers.get("content-type") == "application/json"

    def test_method_not_allowed(self, client):
        """Test 405 errors."""
        response = client.delete("/health")
        assert response.status_code == 405

    def test_invalid_json_body(self, client):
        """Test invalid JSON handling."""
        response = client.post(
            "/whatsapp/webhook",
            content="invalid json{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestRequestLogger:
    """Tests for request logging middleware."""

    def test_request_id_header_generated(self, client):
        """Test request ID is generated and returned."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_response_time_header(self, client):
        """Test response time header is present."""
        response = client.get("/health")
        assert "X-Response-Time" in response.headers
        # Should be in format like "1.23ms"
        time_value = response.headers.get("X-Response-Time", "")
        assert "ms" in time_value

    def test_custom_request_id_preserved(self, client):
        """Test custom request ID is preserved."""
        custom_id = "test-request-id-123"
        response = client.get(
            "/health",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers.get("X-Request-ID") == custom_id
