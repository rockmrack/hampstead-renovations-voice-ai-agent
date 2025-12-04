"""
Pytest configuration and shared fixtures.
"""

import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment variables before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["TESTING"] = "true"
os.environ["DEBUG_MODE"] = "true"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
os.environ["DEEPGRAM_API_KEY"] = "test-deepgram-key"
os.environ["ELEVENLABS_API_KEY"] = "test-elevenlabs-key"
os.environ["VAPI_API_KEY"] = "test-vapi-key"
os.environ["WHATSAPP_API_KEY"] = "test-whatsapp-key"
os.environ["HUBSPOT_API_KEY"] = "test-hubspot-key"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test_db"

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def app():
    """Create FastAPI app instance."""
    from app import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app) -> Generator:
    """Create synchronous test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(app) -> AsyncGenerator:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Mock Services
# =============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.lpush.return_value = 1
    mock.lrange.return_value = []
    mock.hgetall.return_value = {}
    mock.hset.return_value = True
    mock.expire.return_value = True
    mock.delete.return_value = 1
    mock.keys.return_value = []
    mock.zremrangebyscore.return_value = 0
    mock.zcard.return_value = 0
    mock.zadd.return_value = 1
    mock.pipeline.return_value = mock
    mock.execute.return_value = [0, 0, 1, True]
    return mock


@pytest.fixture
def mock_claude_service():
    """Mock Claude AI service."""
    mock = AsyncMock()
    mock.generate_response.return_value = "Thank you for contacting Hampstead Renovations!"
    mock.qualify_lead.return_value = {
        "qualification": {
            "lead_score": 75,
            "lead_tier": "warm",
            "urgency": "this-month",
        },
        "project": {
            "type": "kitchen",
            "timeline": "2-3 months",
        },
        "contact": {
            "name": "John Smith",
            "phone": "+447912345678",
        },
    }
    mock.analyze_sentiment.return_value = {
        "sentiment": "positive",
        "confidence": 0.85,
    }
    return mock


@pytest.fixture
def mock_deepgram_service():
    """Mock Deepgram STT service."""
    mock = AsyncMock()
    mock.transcribe_audio.return_value = "I'm interested in a kitchen renovation."
    mock.transcribe_url.return_value = "Hello, I'd like a quote please."
    return mock


@pytest.fixture
def mock_elevenlabs_service():
    """Mock ElevenLabs TTS service."""
    mock = AsyncMock()
    mock.synthesize_speech.return_value = b"mock audio bytes"
    mock.synthesize_and_upload.return_value = "https://s3.example.com/audio/test.mp3"
    return mock


@pytest.fixture
def mock_whatsapp_service():
    """Mock WhatsApp service."""
    mock = AsyncMock()
    mock.send_text_message.return_value = {"messages": [{"id": "wamid.test"}]}
    mock.send_audio_message.return_value = {"messages": [{"id": "wamid.audio"}]}
    mock.download_media.return_value = b"audio content"
    mock.mark_as_read.return_value = True
    return mock


@pytest.fixture
def mock_hubspot_service():
    """Mock HubSpot CRM service."""
    mock = AsyncMock()
    mock.contact_exists.return_value = False
    mock.get_contact_by_phone.return_value = None
    mock.create_or_update_contact.return_value = {"id": "12345", "properties": {}}
    mock.update_lead_qualification.return_value = {"id": "12345"}
    mock.log_call.return_value = {"id": "call_123"}
    return mock


@pytest.fixture
def mock_calendar_service():
    """Mock Calendar service."""
    mock = AsyncMock()
    mock.get_available_slots.return_value = [
        {"date": "2025-01-15", "time": "10:00", "datetime": "2025-01-15T10:00:00", "duration": 60},
        {"date": "2025-01-15", "time": "14:00", "datetime": "2025-01-15T14:00:00", "duration": 60},
    ]
    mock.create_survey_booking.return_value = "event_123"
    mock.cancel_booking.return_value = True
    mock.reschedule_booking.return_value = True
    return mock


@pytest.fixture
def mock_notification_service():
    """Mock notification service."""
    mock = AsyncMock()
    mock.notify_slack.return_value = True
    mock.notify_escalation.return_value = None
    mock.notify_new_lead.return_value = None
    mock.notify_booking_created.return_value = None
    mock.send_sms_alert.return_value = True
    return mock


# =============================================================================
# Sample Payloads
# =============================================================================

@pytest.fixture
def sample_whatsapp_text_message():
    """Sample WhatsApp text message payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123456789",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "447900000000",
                        "phone_number_id": "123456789"
                    },
                    "contacts": [{"profile": {"name": "John Smith"}, "wa_id": "447912345678"}],
                    "messages": [{
                        "from": "447912345678",
                        "id": "wamid.test123",
                        "timestamp": "1733356800",
                        "text": {"body": "Hi, I'm looking for a kitchen renovation quote in NW3."},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }


@pytest.fixture
def sample_whatsapp_audio_message():
    """Sample WhatsApp audio message payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123456789",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "447900000000",
                        "phone_number_id": "123456789"
                    },
                    "contacts": [{"profile": {"name": "Jane Doe"}, "wa_id": "447987654321"}],
                    "messages": [{
                        "from": "447987654321",
                        "id": "wamid.audio123",
                        "timestamp": "1733356800",
                        "audio": {
                            "mime_type": "audio/ogg; codecs=opus",
                            "sha256": "test-sha",
                            "id": "audio-media-id-123"
                        },
                        "type": "audio"
                    }]
                },
                "field": "messages"
            }]
        }]
    }


@pytest.fixture
def sample_vapi_function_call():
    """Sample VAPI function call webhook payload."""
    return {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "check_availability",
                "parameters": {
                    "preferred_date": "2025-01-15",
                    "postcode": "NW3 2AB"
                }
            },
            "call": {
                "id": "call-test-123",
                "phoneNumber": "+447912345678",
                "customer": {"number": "+447912345678"}
            }
        }
    }


@pytest.fixture
def sample_vapi_call_ended():
    """Sample VAPI call ended webhook payload."""
    return {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "call-test-123",
                "phoneNumber": "+447912345678",
                "customer": {"number": "+447912345678"}
            },
            "endedReason": "customer-ended-call",
            "transcript": "Agent: Hello, Hampstead Renovations...\nCustomer: Hi, I need a quote...",
            "summary": "Customer inquired about kitchen renovation",
            "recordingUrl": "https://storage.example.com/recording.mp3"
        }
    }


@pytest.fixture
def sample_booking_request():
    """Sample survey booking request."""
    return {
        "name": "John Smith",
        "phone": "+447912345678",
        "email": "john@example.com",
        "address": "123 High Street, Hampstead, London",
        "postcode": "NW3 2AB",
        "project_type": "kitchen",
        "date": "2025-01-15",
        "time": "10:00",
        "notes": "Victorian property, ground floor kitchen"
    }
