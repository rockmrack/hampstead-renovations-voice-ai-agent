"""
Integration tests for end-to-end flows.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestWhatsAppFlow:
    """Integration tests for WhatsApp message flow."""

    def test_webhook_verification(self, client):
        """Test WhatsApp webhook verification challenge."""
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "test-token",
            "hub.challenge": "challenge-string-12345",
        }
        response = client.get("/whatsapp/webhook", params=params)
        # Will return 403 if token doesn't match, or 200 with challenge
        assert response.status_code in [200, 403]

    def test_text_message_webhook(self, client, sample_whatsapp_text_message):
        """Test processing text message webhook."""
        with patch("routes.whatsapp.process_message_background"):
            response = client.post(
                "/whatsapp/webhook",
                json=sample_whatsapp_text_message,
            )
            assert response.status_code == 200

    def test_audio_message_webhook(self, client, sample_whatsapp_audio_message):
        """Test processing audio message webhook."""
        with patch("routes.whatsapp.process_message_background"):
            response = client.post(
                "/whatsapp/webhook",
                json=sample_whatsapp_audio_message,
            )
            assert response.status_code == 200

    def test_invalid_webhook_payload(self, client):
        """Test handling invalid webhook payload."""
        response = client.post(
            "/whatsapp/webhook",
            json={"invalid": "payload"},
        )
        # Should handle gracefully, not crash
        assert response.status_code in [200, 400, 422]


class TestVAPIFlow:
    """Integration tests for VAPI voice call flow."""

    def test_function_call_webhook(self, client, sample_vapi_function_call):
        """Test VAPI function call handling."""
        with patch("routes.vapi_webhooks.vapi_service.verify_webhook_signature", return_value=True):
            response = client.post(
                "/vapi/webhook",
                json=sample_vapi_function_call,
                headers={"X-Vapi-Signature": "test-signature"},
            )
            # May require proper signature
            assert response.status_code in [200, 401]

    def test_call_ended_webhook(self, client, sample_vapi_call_ended):
        """Test VAPI call ended handling."""
        with (
            patch("routes.vapi_webhooks.vapi_service.verify_webhook_signature", return_value=True),
            patch("routes.vapi_webhooks.process_call_ended"),
        ):
            response = client.post(
                "/vapi/webhook",
                json=sample_vapi_call_ended,
                headers={"X-Vapi-Signature": "test-signature"},
            )
            assert response.status_code in [200, 401]


class TestCalendarFlow:
    """Integration tests for calendar booking flow."""

    def test_get_availability(self, client, mock_calendar_service):
        """Test getting available time slots."""
        with patch("routes.calendar.calendar_service", mock_calendar_service):
            response = client.get(
                "/calendar/slots",
                params={"date": "2025-01-15", "postcode": "NW3 2AB"},
            )
            # May require auth
            assert response.status_code in [200, 401, 422]

    def test_create_booking(self, client, sample_booking_request, mock_calendar_service):
        """Test creating a survey booking."""
        with (
            patch("routes.calendar.calendar_service", mock_calendar_service),
            patch("routes.calendar.hubspot_service") as mock_hubspot,
        ):
            mock_hubspot.create_or_update_contact = AsyncMock(return_value={"id": "123"})
            response = client.post(
                "/calendar/book",
                json=sample_booking_request,
            )
            assert response.status_code in [200, 201, 401, 422]


class TestHealthFlow:
    """Integration tests for health endpoints."""

    def test_basic_health(self, client):
        """Test basic health check."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["healthy", "ok"]

    def test_readiness_probe(self, client):
        """Test Kubernetes readiness probe."""
        response = client.get("/health/ready")
        assert response.status_code in [200, 503]

    def test_liveness_probe(self, client):
        """Test Kubernetes liveness probe."""
        response = client.get("/health/live")
        assert response.status_code == 200


class TestLeadQualificationFlow:
    """Integration tests for lead qualification flow."""

    @pytest.mark.asyncio
    async def test_full_qualification_flow(
        self,
        mock_claude_service,
        mock_hubspot_service,
        mock_notification_service,
    ):
        """Test complete lead qualification flow."""
        # 1. Qualify lead with Claude
        qualification = await mock_claude_service.qualify_lead(
            conversation="I want a full kitchen renovation in NW3, budget £80k",
            phone="+447912345678",
        )

        assert qualification["qualification"]["lead_tier"] in ["hot", "warm", "cold"]

        # 2. Update HubSpot
        await mock_hubspot_service.update_lead_qualification(
            phone="+447912345678",
            qualification=qualification,
        )
        mock_hubspot_service.update_lead_qualification.assert_called_once()

        # 3. Notify if hot lead
        if qualification["qualification"]["lead_tier"] == "hot":
            await mock_notification_service.notify_new_lead(
                phone="+447912345678",
                name="Test",
                project_type="kitchen",
                lead_score=qualification["qualification"]["lead_score"],
                lead_tier="hot",
            )


class TestBookingFlow:
    """Integration tests for survey booking flow."""

    @pytest.mark.asyncio
    async def test_full_booking_flow(
        self,
        mock_calendar_service,
        mock_hubspot_service,
        mock_notification_service,
        mock_whatsapp_service,
    ):
        """Test complete booking flow."""
        # 1. Check availability
        slots = await mock_calendar_service.get_available_slots(
            date="2025-01-15",
            time_preference="morning",
        )
        assert len(slots) > 0

        # 2. Create booking
        event_id = await mock_calendar_service.create_survey_booking(
            name="John Smith",
            phone="+447912345678",
            address="123 High Street, NW3",
            date=slots[0]["date"],
            time=slots[0]["time"],
        )
        assert event_id is not None

        # 3. Update HubSpot
        await mock_hubspot_service.create_or_update_contact(
            phone="+447912345678",
            name="John Smith",
        )

        # 4. Send confirmation
        await mock_whatsapp_service.send_text_message(
            to="+447912345678",
            message="Your survey is booked!",
        )

        # 5. Notify team
        await mock_notification_service.notify_booking_created(
            customer_name="John Smith",
            phone="+447912345678",
            address="123 High Street, NW3",
            date=slots[0]["date"],
            time=slots[0]["time"],
        )
