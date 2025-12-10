"""
Unit tests for service layer.
"""

from unittest.mock import patch

import pytest


class TestClaudeService:
    """Tests for Claude AI service."""

    @pytest.mark.asyncio
    async def test_generate_response_success(self, mock_claude_service):
        """Test successful response generation."""
        response = await mock_claude_service.generate_response(
            message="Hello, I need a quote",
            phone="+447912345678",
            conversation_history="",
        )
        assert response is not None
        assert "Hampstead" in response

    @pytest.mark.asyncio
    async def test_qualify_lead_returns_score(self, mock_claude_service):
        """Test lead qualification returns expected structure."""
        result = await mock_claude_service.qualify_lead(
            conversation="I want to renovate my kitchen in Hampstead",
            phone="+447912345678",
        )

        assert "qualification" in result
        assert "lead_score" in result["qualification"]
        assert result["qualification"]["lead_score"] >= 0
        assert result["qualification"]["lead_score"] <= 100

    @pytest.mark.asyncio
    async def test_analyze_sentiment(self, mock_claude_service):
        """Test sentiment analysis."""
        result = await mock_claude_service.analyze_sentiment(
            message="I'm very happy with the service!"
        )

        assert "sentiment" in result
        assert result["sentiment"] in ["positive", "neutral", "negative", "frustrated"]


class TestDeepgramService:
    """Tests for Deepgram STT service."""

    @pytest.mark.asyncio
    async def test_transcribe_audio_bytes(self, mock_deepgram_service):
        """Test transcription from audio bytes."""
        transcript = await mock_deepgram_service.transcribe_audio(audio_data=b"mock audio data")
        assert transcript is not None
        assert len(transcript) > 0

    @pytest.mark.asyncio
    async def test_transcribe_url(self, mock_deepgram_service):
        """Test transcription from URL."""
        transcript = await mock_deepgram_service.transcribe_url(
            audio_url="https://example.com/audio.ogg"
        )
        assert transcript is not None


class TestElevenLabsService:
    """Tests for ElevenLabs TTS service."""

    @pytest.mark.asyncio
    async def test_synthesize_speech(self, mock_elevenlabs_service):
        """Test speech synthesis."""
        audio = await mock_elevenlabs_service.synthesize_speech(text="Hello, this is a test.")
        assert audio is not None
        assert isinstance(audio, bytes)

    @pytest.mark.asyncio
    async def test_synthesize_and_upload(self, mock_elevenlabs_service):
        """Test synthesis with S3 upload."""
        url = await mock_elevenlabs_service.synthesize_and_upload(
            text="Hello, this is a test.",
            filename="test.mp3",
        )
        assert url is not None
        assert url.startswith("https://")


class TestWhatsAppService:
    """Tests for WhatsApp service."""

    @pytest.mark.asyncio
    async def test_send_text_message(self, mock_whatsapp_service):
        """Test sending text message."""
        result = await mock_whatsapp_service.send_text_message(
            to="+447912345678",
            message="Hello!",
        )
        assert "messages" in result
        assert len(result["messages"]) > 0

    @pytest.mark.asyncio
    async def test_send_audio_message(self, mock_whatsapp_service):
        """Test sending audio message."""
        result = await mock_whatsapp_service.send_audio_message(
            to="+447912345678",
            audio_url="https://example.com/audio.mp3",
        )
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_download_media(self, mock_whatsapp_service):
        """Test downloading media."""
        content = await mock_whatsapp_service.download_media(media_id="media123")
        assert content is not None
        assert isinstance(content, bytes)


class TestHubSpotService:
    """Tests for HubSpot CRM service."""

    @pytest.mark.asyncio
    async def test_contact_exists(self, mock_hubspot_service):
        """Test checking if contact exists."""
        exists = await mock_hubspot_service.contact_exists(phone="+447912345678")
        assert isinstance(exists, bool)

    @pytest.mark.asyncio
    async def test_create_contact(self, mock_hubspot_service):
        """Test creating a contact."""
        result = await mock_hubspot_service.create_or_update_contact(
            phone="+447912345678",
            name="John Smith",
            email="john@example.com",
        )
        assert "id" in result

    @pytest.mark.asyncio
    async def test_update_lead_qualification(self, mock_hubspot_service):
        """Test updating lead qualification."""
        result = await mock_hubspot_service.update_lead_qualification(
            phone="+447912345678",
            qualification={
                "qualification": {"lead_score": 80, "lead_tier": "hot"},
                "project": {"type": "kitchen"},
                "contact": {},
            },
        )
        assert result is not None


class TestCalendarService:
    """Tests for Calendar service."""

    @pytest.mark.asyncio
    async def test_get_available_slots(self, mock_calendar_service):
        """Test getting available slots."""
        slots = await mock_calendar_service.get_available_slots(
            date="2025-01-15",
            time_preference="morning",
        )
        assert isinstance(slots, list)
        assert len(slots) > 0
        assert "date" in slots[0]
        assert "time" in slots[0]

    @pytest.mark.asyncio
    async def test_create_booking(self, mock_calendar_service):
        """Test creating a booking."""
        event_id = await mock_calendar_service.create_survey_booking(
            name="John Smith",
            phone="+447912345678",
            address="123 High Street, NW3",
            date="2025-01-15",
            time="10:00",
        )
        assert event_id is not None

    @pytest.mark.asyncio
    async def test_cancel_booking(self, mock_calendar_service):
        """Test cancelling a booking."""
        result = await mock_calendar_service.cancel_booking(event_id="event_123")
        assert result is True


class TestConversationService:
    """Tests for Conversation memory service."""

    @pytest.mark.asyncio
    async def test_get_history_empty(self, mock_redis):
        """Test getting empty conversation history."""
        with patch(
            "services.conversation_service.conversation_service._get_redis", return_value=mock_redis
        ):
            from services.conversation_service import conversation_service

            mock_redis.lrange.return_value = []
            history = await conversation_service.get_conversation_history(phone="+447912345678")
            assert history == ""

    @pytest.mark.asyncio
    async def test_add_message(self, mock_redis):
        """Test adding message to history."""
        with patch(
            "services.conversation_service.conversation_service._get_redis", return_value=mock_redis
        ):
            from services.conversation_service import conversation_service

            await conversation_service.add_message(
                phone="+447912345678",
                role="customer",
                content="Hello!",
            )
            mock_redis.lpush.assert_called()


class TestNotificationService:
    """Tests for Notification service."""

    @pytest.mark.asyncio
    async def test_notify_slack(self, mock_notification_service):
        """Test Slack notification."""
        result = await mock_notification_service.notify_slack(message="Test notification")
        assert result is True

    @pytest.mark.asyncio
    async def test_notify_escalation(self, mock_notification_service):
        """Test escalation notification."""
        await mock_notification_service.notify_escalation(
            phone="+447912345678",
            reason="Customer upset",
            conversation="Recent messages...",
            urgency="immediate",
        )
        mock_notification_service.notify_escalation.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_new_lead(self, mock_notification_service):
        """Test new lead notification."""
        await mock_notification_service.notify_new_lead(
            phone="+447912345678",
            name="John Smith",
            project_type="kitchen",
            lead_score=85,
            lead_tier="hot",
        )
        mock_notification_service.notify_new_lead.assert_called_once()
