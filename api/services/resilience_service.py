"""
Resilience Service for Hampstead Renovations Voice AI Agent

Provides offline fallback and graceful degradation:
- Local response cache for common queries
- Fallback responses when services are unavailable
- Circuit breaker pattern implementation
- Service health monitoring
"""

import asyncio
import logging
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import hashlib
import redis.asyncio as redis
from config import settings

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Status of external services"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, use fallback
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class ServiceHealth:
    """Health status of a service"""
    name: str
    status: ServiceStatus
    last_check: datetime
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    average_latency_ms: float = 0.0
    error_rate: float = 0.0


@dataclass
class CircuitBreaker:
    """Circuit breaker for a service"""
    service_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    open_until: Optional[datetime] = None
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 30
    half_open_max_calls: int = 3


class ResilienceService:
    """
    Resilience and fallback service
    
    Provides:
    - Response caching for common queries
    - Circuit breaker pattern for external services
    - Graceful degradation strategies
    - Fallback responses
    """
    
    # Fallback responses for common queries
    FALLBACK_RESPONSES = {
        "greeting": "Hello! Thank you for contacting Hampstead Renovations. I'm currently experiencing some technical difficulties, but I'd love to help you. Could you please share your phone number and someone from our team will call you back shortly?",
        
        "services": """Hampstead Renovations specializes in:

• Kitchen extensions and renovations
• Bathroom refurbishments
• Loft conversions
• Full house renovations
• Period property restoration

We serve North West London including Hampstead, Highgate, Primrose Hill, and surrounding areas.

Would you like to schedule a consultation? Please share your contact details and we'll be in touch.""",

        "pricing": """Our project prices typically range:

• Kitchen renovations: £25,000 - £75,000
• Bathroom refurbishments: £15,000 - £45,000
• Loft conversions: £45,000 - £150,000
• Extensions: £75,000 - £220,000
• Full renovations: £150,000+

Every project is unique, so we provide detailed quotes after a site visit. Would you like to book a free consultation?""",

        "availability": "I'm having trouble checking our live calendar right now. Our team typically has availability for consultations within the next 2 weeks. Please share your preferred date and contact number, and we'll confirm your appointment shortly.",
        
        "contact": """You can reach Hampstead Renovations at:

📞 Phone: 020 7123 4567
📧 Email: hello@hampstead-renovations.com
📍 Office: 123 High Street, Hampstead, London NW3

Or share your details and we'll call you back!""",

        "hours": """Our office hours are:

Monday - Friday: 8:00 AM - 6:00 PM
Saturday: 9:00 AM - 2:00 PM
Sunday: Closed

For emergencies on active projects, our project managers are available 24/7.""",

        "error": "I apologize, but I'm experiencing some technical difficulties right now. Please try again in a moment, or call us directly at 020 7123 4567. We're here to help!"
    }
    
    # Common question patterns for cache matching
    QUERY_PATTERNS = {
        "greeting": ["hello", "hi", "hey", "good morning", "good afternoon"],
        "services": ["what do you do", "services", "what can you", "types of", "renovations"],
        "pricing": ["price", "cost", "how much", "budget", "quote", "estimate"],
        "availability": ["available", "when can", "book", "appointment", "schedule", "calendar"],
        "contact": ["phone", "email", "contact", "address", "reach you", "call"],
        "hours": ["open", "hours", "when are you", "times", "working hours"]
    }
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._service_health: dict[str, ServiceHealth] = {}
        self._response_cache: dict[str, tuple[str, datetime]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True
            )
            await self._redis.ping()
            logger.info("ResilienceService initialized with Redis")
        except Exception as e:
            logger.warning(f"Redis unavailable, using in-memory fallback: {e}")
            self._redis = None
            
        # Initialize circuit breakers for key services
        services = ["claude", "deepgram", "elevenlabs", "hubspot", "calendar", "whatsapp"]
        for service in services:
            self._circuit_breakers[service] = CircuitBreaker(service_name=service)
            self._service_health[service] = ServiceHealth(
                name=service,
                status=ServiceStatus.HEALTHY,
                last_check=datetime.utcnow()
            )
            
    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for a service"""
        if service_name not in self._circuit_breakers:
            self._circuit_breakers[service_name] = CircuitBreaker(service_name=service_name)
        return self._circuit_breakers[service_name]
        
    async def execute_with_fallback(
        self,
        service_name: str,
        operation: Callable,
        fallback_response: Any,
        *args,
        **kwargs
    ) -> tuple[Any, bool]:
        """
        Execute an operation with circuit breaker and fallback
        
        Args:
            service_name: Name of the service
            operation: Async function to execute
            fallback_response: Response to return if operation fails
            *args, **kwargs: Arguments for the operation
            
        Returns:
            Tuple of (result, used_fallback)
        """
        circuit = self.get_circuit_breaker(service_name)
        
        # Check circuit state
        if circuit.state == CircuitState.OPEN:
            if datetime.utcnow() >= circuit.open_until:
                # Try half-open
                circuit.state = CircuitState.HALF_OPEN
                circuit.success_count = 0
            else:
                # Circuit open, use fallback
                logger.warning(f"Circuit open for {service_name}, using fallback")
                return fallback_response, True
                
        try:
            # Execute operation
            start_time = datetime.utcnow()
            result = await operation(*args, **kwargs)
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Record success
            await self._record_success(service_name, latency)
            
            return result, False
            
        except Exception as e:
            # Record failure
            await self._record_failure(service_name, str(e))
            
            logger.error(f"Service {service_name} failed: {e}, using fallback")
            return fallback_response, True
            
    async def _record_success(self, service_name: str, latency_ms: float):
        """Record a successful operation"""
        circuit = self.get_circuit_breaker(service_name)
        health = self._service_health.get(service_name)
        
        circuit.success_count += 1
        circuit.failure_count = 0
        circuit.last_success = datetime.utcnow()
        
        if circuit.state == CircuitState.HALF_OPEN:
            if circuit.success_count >= circuit.half_open_max_calls:
                circuit.state = CircuitState.CLOSED
                logger.info(f"Circuit closed for {service_name}")
                
        if health:
            health.consecutive_successes += 1
            health.consecutive_failures = 0
            health.status = ServiceStatus.HEALTHY
            health.last_check = datetime.utcnow()
            # Update average latency (simple moving average)
            health.average_latency_ms = (health.average_latency_ms * 0.9) + (latency_ms * 0.1)
            
    async def _record_failure(self, service_name: str, error: str):
        """Record a failed operation"""
        circuit = self.get_circuit_breaker(service_name)
        health = self._service_health.get(service_name)
        
        circuit.failure_count += 1
        circuit.success_count = 0
        circuit.last_failure = datetime.utcnow()
        
        if circuit.failure_count >= circuit.failure_threshold:
            circuit.state = CircuitState.OPEN
            circuit.open_until = datetime.utcnow() + timedelta(seconds=circuit.recovery_timeout_seconds)
            logger.warning(f"Circuit opened for {service_name}, will retry at {circuit.open_until}")
            
        if health:
            health.consecutive_failures += 1
            health.consecutive_successes = 0
            health.last_check = datetime.utcnow()
            
            if health.consecutive_failures >= 3:
                health.status = ServiceStatus.UNAVAILABLE
            elif health.consecutive_failures >= 1:
                health.status = ServiceStatus.DEGRADED
                
    async def cache_response(self, query: str, response: str):
        """Cache a response for a query"""
        cache_key = self._generate_cache_key(query)
        
        if self._redis:
            await self._redis.setex(
                f"response_cache:{cache_key}",
                self._cache_ttl_seconds,
                response
            )
        else:
            self._response_cache[cache_key] = (response, datetime.utcnow())
            
    async def get_cached_response(self, query: str) -> Optional[str]:
        """Get a cached response for a query"""
        cache_key = self._generate_cache_key(query)
        
        if self._redis:
            cached = await self._redis.get(f"response_cache:{cache_key}")
            return cached
        else:
            cached = self._response_cache.get(cache_key)
            if cached:
                response, timestamp = cached
                if datetime.utcnow() - timestamp < timedelta(seconds=self._cache_ttl_seconds):
                    return response
            return None
            
    def _generate_cache_key(self, query: str) -> str:
        """Generate a cache key from query"""
        # Normalize query
        normalized = query.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()
        
    def get_fallback_response(self, query: str) -> str:
        """Get appropriate fallback response for a query"""
        query_lower = query.lower()
        
        # Match against patterns
        for category, patterns in self.QUERY_PATTERNS.items():
            for pattern in patterns:
                if pattern in query_lower:
                    return self.FALLBACK_RESPONSES.get(category, self.FALLBACK_RESPONSES["error"])
                    
        # Default fallback
        return self.FALLBACK_RESPONSES["error"]
        
    async def get_service_health(self, service_name: Optional[str] = None) -> dict:
        """Get health status of services"""
        if service_name:
            health = self._service_health.get(service_name)
            if health:
                return {
                    "name": health.name,
                    "status": health.status.value,
                    "last_check": health.last_check.isoformat(),
                    "consecutive_failures": health.consecutive_failures,
                    "average_latency_ms": health.average_latency_ms
                }
            return {"error": f"Unknown service: {service_name}"}
            
        # Return all services
        return {
            name: {
                "status": h.status.value,
                "last_check": h.last_check.isoformat(),
                "consecutive_failures": h.consecutive_failures,
                "average_latency_ms": h.average_latency_ms
            }
            for name, h in self._service_health.items()
        }
        
    async def get_circuit_status(self, service_name: Optional[str] = None) -> dict:
        """Get circuit breaker status"""
        if service_name:
            circuit = self._circuit_breakers.get(service_name)
            if circuit:
                return {
                    "service": circuit.service_name,
                    "state": circuit.state.value,
                    "failure_count": circuit.failure_count,
                    "last_failure": circuit.last_failure.isoformat() if circuit.last_failure else None,
                    "open_until": circuit.open_until.isoformat() if circuit.open_until else None
                }
            return {"error": f"Unknown service: {service_name}"}
            
        return {
            name: {
                "state": c.state.value,
                "failure_count": c.failure_count,
                "last_failure": c.last_failure.isoformat() if c.last_failure else None
            }
            for name, c in self._circuit_breakers.items()
        }
        
    async def is_degraded_mode(self) -> bool:
        """Check if system is in degraded mode"""
        critical_services = ["claude", "whatsapp"]
        
        for service in critical_services:
            health = self._service_health.get(service)
            if health and health.status == ServiceStatus.UNAVAILABLE:
                return True
                
        return False
        
    async def get_degradation_message(self) -> Optional[str]:
        """Get message explaining current degradation"""
        unavailable = []
        degraded = []
        
        for name, health in self._service_health.items():
            if health.status == ServiceStatus.UNAVAILABLE:
                unavailable.append(name)
            elif health.status == ServiceStatus.DEGRADED:
                degraded.append(name)
                
        if not unavailable and not degraded:
            return None
            
        parts = []
        if unavailable:
            parts.append(f"Services unavailable: {', '.join(unavailable)}")
        if degraded:
            parts.append(f"Services degraded: {', '.join(degraded)}")
            
        return ". ".join(parts)
        
    async def warm_cache(self, common_responses: dict[str, str]):
        """Pre-populate cache with common responses"""
        for query, response in common_responses.items():
            await self.cache_response(query, response)
        logger.info(f"Warmed cache with {len(common_responses)} responses")
        
    def reset_circuit(self, service_name: str):
        """Manually reset a circuit breaker"""
        if service_name in self._circuit_breakers:
            circuit = self._circuit_breakers[service_name]
            circuit.state = CircuitState.CLOSED
            circuit.failure_count = 0
            circuit.success_count = 0
            circuit.open_until = None
            logger.info(f"Circuit reset for {service_name}")
            
    async def health_check_all(self) -> dict:
        """Perform health check on all monitored services"""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy",
            "services": await self.get_service_health(),
            "circuits": await self.get_circuit_status(),
            "degraded_mode": await self.is_degraded_mode()
        }
        
        # Determine overall status
        unhealthy_count = sum(
            1 for h in self._service_health.values()
            if h.status != ServiceStatus.HEALTHY
        )
        
        if unhealthy_count >= len(self._service_health) / 2:
            results["overall_status"] = "critical"
        elif unhealthy_count > 0:
            results["overall_status"] = "degraded"
            
        return results


# Module-level instance
resilience_service = ResilienceService()
