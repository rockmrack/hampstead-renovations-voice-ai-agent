"""
Prometheus metrics setup and utilities.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import structlog

logger = structlog.get_logger(__name__)

# ============================================
# Metric Definitions
# ============================================

# Request metrics
REQUEST_COUNT = Counter(
    "voice_agent_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "voice_agent_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Conversation metrics
CONVERSATION_COUNT = Counter(
    "voice_agent_conversations_total",
    "Total number of conversations",
    ["channel", "type"],  # channel: whatsapp/phone, type: text/voice_note/call
)

MESSAGE_COUNT = Counter(
    "voice_agent_messages_total",
    "Total messages processed",
    ["direction", "channel"],  # direction: inbound/outbound
)

# AI service metrics
AI_REQUESTS = Counter(
    "voice_agent_ai_requests_total",
    "Total AI service requests",
    ["service", "operation"],  # service: claude/deepgram/elevenlabs
)

AI_LATENCY = Histogram(
    "voice_agent_ai_latency_seconds",
    "AI service latency",
    ["service", "operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

AI_ERRORS = Counter(
    "voice_agent_ai_errors_total",
    "AI service errors",
    ["service", "error_type"],
)

# Lead qualification metrics
LEAD_QUALIFICATIONS = Counter(
    "voice_agent_lead_qualifications_total",
    "Lead qualifications performed",
    ["tier"],  # hot/warm/cold/unqualified
)

LEAD_SCORE = Histogram(
    "voice_agent_lead_score",
    "Lead score distribution",
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)

# Booking metrics
BOOKING_ATTEMPTS = Counter(
    "voice_agent_booking_attempts_total",
    "Survey booking attempts",
    ["status"],  # success/failure/slot_unavailable
)

BOOKINGS_CREATED = Counter(
    "voice_agent_bookings_created_total",
    "Total bookings created",
)

# External service metrics
EXTERNAL_SERVICE_CALLS = Counter(
    "voice_agent_external_service_calls_total",
    "External service API calls",
    ["service", "status"],  # service: hubspot/microsoft/360dialog
)

EXTERNAL_SERVICE_LATENCY = Histogram(
    "voice_agent_external_service_latency_seconds",
    "External service latency",
    ["service"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# Active connections gauge
ACTIVE_CONVERSATIONS = Gauge(
    "voice_agent_active_conversations",
    "Currently active conversations",
    ["channel"],
)

# Error metrics
ERROR_COUNT = Counter(
    "voice_agent_errors_total",
    "Total errors",
    ["type", "endpoint"],
)


# ============================================
# Metrics Middleware
# ============================================

class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track request metrics."""

    async def dispatch(self, request: Request, call_next):
        # Skip metrics endpoint
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = self._get_endpoint(request.url.path)
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            
            # Track metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint,
            ).observe(time.time() - start_time)
            
            return response
            
        except Exception as exc:
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code="500",
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint,
            ).observe(time.time() - start_time)
            
            raise

    def _get_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics."""
        # Remove specific IDs to avoid cardinality explosion
        parts = path.strip("/").split("/")
        
        # Keep first 3 parts: /api/v1/endpoint
        if len(parts) > 3:
            return "/" + "/".join(parts[:3])
        
        return path


# ============================================
# Setup Function
# ============================================

def setup_metrics(app: FastAPI) -> None:
    """
    Configure metrics for the FastAPI application.
    
    Adds:
    - Metrics middleware for request tracking
    - /metrics endpoint for Prometheus scraping
    """
    # Add metrics middleware
    app.add_middleware(MetricsMiddleware)
    
    # Add metrics endpoint
    @app.get("/metrics")
    async def metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
    
    logger.info("metrics_configured")


# ============================================
# Tracking Utilities
# ============================================

def track_request(method: str, endpoint: str, status_code: int, duration: float) -> None:
    """Track a request metric."""
    REQUEST_COUNT.labels(
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()
    
    REQUEST_DURATION.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration)


def track_conversation(channel: str, message_type: str) -> None:
    """Track a conversation metric."""
    CONVERSATION_COUNT.labels(
        channel=channel,
        type=message_type,
    ).inc()


def track_message(direction: str, channel: str) -> None:
    """Track a message metric."""
    MESSAGE_COUNT.labels(
        direction=direction,
        channel=channel,
    ).inc()


def track_ai_request(service: str, operation: str, duration: float) -> None:
    """Track an AI service request."""
    AI_REQUESTS.labels(
        service=service,
        operation=operation,
    ).inc()
    
    AI_LATENCY.labels(
        service=service,
        operation=operation,
    ).observe(duration)


def track_ai_error(service: str, error_type: str) -> None:
    """Track an AI service error."""
    AI_ERRORS.labels(
        service=service,
        error_type=error_type,
    ).inc()


def track_lead_qualification(tier: str, score: int) -> None:
    """Track a lead qualification."""
    LEAD_QUALIFICATIONS.labels(tier=tier).inc()
    LEAD_SCORE.observe(score)


def track_booking(status: str) -> None:
    """Track a booking attempt."""
    BOOKING_ATTEMPTS.labels(status=status).inc()
    if status == "success":
        BOOKINGS_CREATED.inc()


def track_external_service(service: str, status: str, duration: float) -> None:
    """Track an external service call."""
    EXTERNAL_SERVICE_CALLS.labels(
        service=service,
        status=status,
    ).inc()
    
    EXTERNAL_SERVICE_LATENCY.labels(
        service=service,
    ).observe(duration)


def set_active_conversations(channel: str, count: int) -> None:
    """Set the active conversations gauge."""
    ACTIVE_CONVERSATIONS.labels(channel=channel).set(count)


def track_error(error_type: str, endpoint: str) -> None:
    """Track an error."""
    ERROR_COUNT.labels(
        type=error_type,
        endpoint=endpoint,
    ).inc()
