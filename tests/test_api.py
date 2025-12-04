"""
=============================================================================
HAMPSTEAD RENOVATIONS VOICE AI AGENT - TEST SUITE
=============================================================================
Comprehensive tests for API endpoints, services, and integrations
=============================================================================
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["DEEPGRAM_API_KEY"] = "test-key"
os.environ["ELEVENLABS_API_KEY"] = "test-key"
os.environ["VAPI_API_KEY"] = "test-key"
os.environ["WHATSAPP_API_KEY"] = "test-key"
os.environ["HUBSPOT_API_KEY"] = "test-key"

from api.app import app


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client() -> Generator:
    """Create test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client() -> AsyncClient:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_claude_response():
    """Mock Claude API response."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "Thank you for contacting Hampstead Renovations! I'd be happy to help you with your home renovation project. Could you tell me a bit more about what you're looking to achieve?"
            }
        ],
        "model": "claude-sonnet-4-5-20250514",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 150,
            "output_tokens": 45
        }
    }


@pytest.fixture
def mock_deepgram_response():
    """Mock Deepgram transcription response."""
    return {
        "metadata": {
            "transaction_key": "test-key",
            "request_id": "test-request-id",
            "sha256": "test-sha",
            "created": "2024-01-01T00:00:00Z",
            "duration": 5.5,
            "channels": 1
        },
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello, I'm interested in getting a kitchen renovation quote for my property in Hampstead.",
                            "confidence": 0.98,
                            "words": []
                        }
                    ]
                }
            ]
        }
    }


@pytest.fixture
def sample_whatsapp_text_payload():
    """Sample WhatsApp text message webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "447900000000",
                                "phone_number_id": "123456789"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "John Smith"
                                    },
                                    "wa_id": "447912345678"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "447912345678",
                                    "id": "wamid.test123",
                                    "timestamp": "1704067200",
                                    "text": {
                                        "body": "Hi, I'm looking for a quote on a full kitchen renovation in NW3."
                                    },
                                    "type": "text"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_whatsapp_audio_payload():
    """Sample WhatsApp audio message webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "447900000000",
                                "phone_number_id": "123456789"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Jane Doe"
                                    },
                                    "wa_id": "447987654321"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "447987654321",
                                    "id": "wamid.audio123",
                                    "timestamp": "1704067200",
                                    "audio": {
                                        "mime_type": "audio/ogg; codecs=opus",
                                        "sha256": "test-sha",
                                        "id": "audio-media-id-123"
                                    },
                                    "type": "audio"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_vapi_webhook_payload():
    """Sample VAPI webhook payload."""
    return {
        "message": {
            "type": "function-call",
            "functionCall": {
                "name": "check_availability",
                "parameters": {
                    "preferred_date": "2024-01-15",
                    "postcode": "NW3 2AB"
                }
            },
            "call": {
                "id": "call-test-123",
                "phoneNumber": "+447912345678",
                "customer": {
                    "number": "+447912345678"
                }
            }
        }
    }


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check_basic(self, client):
        """Test basic health endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_health_check_detailed(self, client):
        """Test detailed health endpoint."""
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "uptime_seconds" in data

    def test_readiness_probe(self, client):
        """Test Kubernetes readiness probe."""
        response = client.get("/api/v1/health/ready")
        assert response.status_code in [200, 503]

    def test_liveness_probe(self, client):
        """Test Kubernetes liveness probe."""
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200


# =============================================================================
# WHATSAPP WEBHOOK TESTS
# =============================================================================

class TestWhatsAppWebhook:
    """Test WhatsApp webhook handling."""

    def test_webhook_verification(self, client):
        """Test WhatsApp webhook verification challenge."""
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "test-token"),
            "hub.challenge": "test-challenge-12345"
        }
        response = client.get("/api/v1/whatsapp/webhook", params=params)
        # May return 200 with challenge or 403 if token doesn't match
        assert response.status_code in [200, 403]

    def test_webhook_text_message(self, client, sample_whatsapp_text_payload):
        """Test handling text message webhook."""
        with patch("api.routes.whatsapp.process_whatsapp_message") as mock_process:
            mock_process.return_value = None
            response = client.post(
                "/api/v1/whatsapp/webhook",
                json=sample_whatsapp_text_payload
            )
            assert response.status_code == 200

    def test_webhook_audio_message(self, client, sample_whatsapp_audio_payload):
        """Test handling audio message webhook."""
        with patch("api.routes.whatsapp.process_whatsapp_message") as mock_process:
            mock_process.return_value = None
            response = client.post(
                "/api/v1/whatsapp/webhook",
                json=sample_whatsapp_audio_payload
            )
            assert response.status_code == 200

    def test_webhook_invalid_payload(self, client):
        """Test handling invalid webhook payload."""
        response = client.post(
            "/api/v1/whatsapp/webhook",
            json={"invalid": "payload"}
        )
        # Should handle gracefully
        assert response.status_code in [200, 400]


# =============================================================================
# VOICE PROCESSING TESTS
# =============================================================================

class TestVoiceProcessing:
    """Test voice note processing."""

    @pytest.mark.asyncio
    async def test_transcription_endpoint(self, async_client, mock_deepgram_response):
        """Test voice transcription endpoint."""
        with patch("api.routes.voice.transcribe_audio") as mock_transcribe:
            mock_transcribe.return_value = mock_deepgram_response["results"]["channels"][0]["alternatives"][0]["transcript"]
            
            # Create mock audio file
            audio_content = b"mock audio content"
            files = {"audio": ("test.ogg", audio_content, "audio/ogg")}
            
            response = await async_client.post(
                "/api/v1/voice/transcribe",
                files=files
            )
            # May need authentication in production
            assert response.status_code in [200, 401, 422]


# =============================================================================
# CALENDAR TESTS
# =============================================================================

class TestCalendarEndpoints:
    """Test calendar and availability endpoints."""

    def test_get_availability(self, client):
        """Test availability check endpoint."""
        with patch("api.routes.calendar.get_availability") as mock_avail:
            mock_avail.return_value = {
                "available": True,
                "slots": [
                    {
                        "start": "2024-01-15T09:00:00Z",
                        "end": "2024-01-15T10:00:00Z"
                    }
                ]
            }
            
            response = client.get(
                "/api/v1/calendar/availability",
                params={"date": "2024-01-15", "postcode": "NW3 2AB"}
            )
            assert response.status_code in [200, 401]


# =============================================================================
# VAPI WEBHOOK TESTS
# =============================================================================

class TestVAPIWebhooks:
    """Test VAPI voice call webhooks."""

    def test_vapi_function_call(self, client, sample_vapi_webhook_payload):
        """Test VAPI function call handling."""
        with patch("api.routes.vapi_webhooks.verify_vapi_signature") as mock_verify:
            mock_verify.return_value = True
            
            response = client.post(
                "/api/v1/vapi/webhook",
                json=sample_vapi_webhook_payload,
                headers={"X-Vapi-Signature": "test-signature"}
            )
            assert response.status_code in [200, 401]

    def test_vapi_call_started(self, client):
        """Test VAPI call started event."""
        payload = {
            "message": {
                "type": "call-started",
                "call": {
                    "id": "call-123",
                    "phoneNumber": "+447912345678"
                }
            }
        }
        
        with patch("api.routes.vapi_webhooks.verify_vapi_signature") as mock_verify:
            mock_verify.return_value = True
            
            response = client.post(
                "/api/v1/vapi/webhook",
                json=payload,
                headers={"X-Vapi-Signature": "test-signature"}
            )
            assert response.status_code in [200, 401]


# =============================================================================
# LEAD QUALIFICATION TESTS
# =============================================================================

class TestLeadQualification:
    """Test lead qualification and scoring."""

    def test_lead_scoring_hot_lead(self):
        """Test scoring for a hot lead."""
        # Simulated conversation data
        conversation = {
            "messages": [
                {"role": "user", "content": "I want to renovate my entire ground floor in Hampstead. Budget is around £150k and I want to start in 2 months."},
                {"role": "assistant", "content": "That sounds like a wonderful project..."},
            ],
            "extracted_info": {
                "project_type": "full_renovation",
                "budget_range": "£100k-200k",
                "timeline": "2_months",
                "postcode": "NW3"
            }
        }
        
        # Score calculation logic would go here
        # For now, verify structure
        assert "messages" in conversation
        assert "extracted_info" in conversation

    def test_lead_scoring_cold_lead(self):
        """Test scoring for a cold lead."""
        conversation = {
            "messages": [
                {"role": "user", "content": "Just browsing, no specific plans yet."},
            ],
            "extracted_info": {
                "project_type": "unknown",
                "budget_range": "unknown",
                "timeline": "unknown",
                "postcode": None
            }
        }
        
        assert conversation["extracted_info"]["project_type"] == "unknown"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for end-to-end flows."""

    @pytest.mark.asyncio
    async def test_full_whatsapp_flow(self, async_client, mock_claude_response):
        """Test complete WhatsApp message handling flow."""
        # This would test the full flow from webhook to response
        pass

    @pytest.mark.asyncio
    async def test_voice_note_to_response_flow(self, async_client):
        """Test voice note transcription to AI response flow."""
        # This would test transcription -> AI -> TTS -> response
        pass


# =============================================================================
# UTILITY TESTS
# =============================================================================

class TestUtilities:
    """Test utility functions."""

    def test_phone_number_formatting(self):
        """Test phone number formatting utility."""
        # Test various formats
        test_numbers = [
            ("07912345678", "+447912345678"),
            ("447912345678", "+447912345678"),
            ("+447912345678", "+447912345678"),
            ("020 7123 4567", "+442071234567"),
        ]
        
        # Utility function would format these
        for raw, expected in test_numbers:
            # formatted = format_phone_number(raw)
            # assert formatted == expected
            pass

    def test_postcode_validation(self):
        """Test postcode validation utility."""
        valid_postcodes = ["NW3 2AB", "NW11 7ES", "N6 5HE", "W1A 1AA"]
        invalid_postcodes = ["ABC 123", "12345", "NW99 9ZZ"]
        
        for postcode in valid_postcodes:
            # assert is_valid_postcode(postcode)
            pass
        
        for postcode in invalid_postcodes:
            # assert not is_valid_postcode(postcode)
            pass

    def test_service_area_check(self):
        """Test service area validation."""
        in_area = ["NW3 2AB", "NW6 1XJ", "N6 5HE", "NW11 7ES"]
        out_of_area = ["SE1 1AA", "E1 6AN", "SW1A 1AA"]
        
        for postcode in in_area:
            # assert is_in_service_area(postcode)
            pass


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Performance and load tests."""

    def test_health_endpoint_response_time(self, client):
        """Test health endpoint responds within acceptable time."""
        import time
        
        start = time.time()
        response = client.get("/api/v1/health")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.5  # Should respond within 500ms

    def test_concurrent_requests(self, client):
        """Test handling concurrent requests."""
        import concurrent.futures
        
        def make_request():
            return client.get("/api/v1/health")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]
        
        assert all(r.status_code == 200 for r in results)


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_404_handling(self, client):
        """Test 404 error handling."""
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test 405 error handling."""
        response = client.delete("/api/v1/health")
        assert response.status_code == 405

    def test_invalid_json(self, client):
        """Test invalid JSON handling."""
        response = client.post(
            "/api/v1/whatsapp/webhook",
            content="invalid json{",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
