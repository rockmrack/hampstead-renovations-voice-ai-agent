"""Health check endpoints for monitoring and orchestration."""

from datetime import datetime

import structlog
from fastapi import APIRouter, Response

from config import settings

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """
    Basic health check endpoint.
    Returns service status and version information.
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/ready")
async def readiness_check() -> dict:
    """
    Readiness probe for Kubernetes/container orchestration.
    Checks if the service is ready to accept traffic.
    """
    checks = {
        "api": True,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Check external service connectivity
    try:
        # TODO: Add actual health checks for:
        # - Database connectivity
        # - Redis connectivity
        # - External API reachability
        checks["database"] = True
        checks["redis"] = True
        checks["external_apis"] = True
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        checks["error"] = str(e)

    all_healthy = all(v for k, v in checks.items() if k not in ["timestamp", "error"])

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
    }


@router.get("/health/live")
async def liveness_check() -> dict:
    """
    Liveness probe for Kubernetes/container orchestration.
    Checks if the service is alive and should not be restarted.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.head("/health")
async def health_head() -> Response:
    """HEAD request for health check (for load balancers)."""
    return Response(status_code=200)
