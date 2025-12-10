"""
ElevenLabs text-to-speech service.
Handles voice synthesis with Sarah voice optimized for British accent.
"""

import httpx
import structlog
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class ElevenLabsService:
    """Service for ElevenLabs text-to-speech synthesis."""

    def __init__(self):
        self.api_key = settings.elevenlabs_api_key
        self.base_url = "https://api.elevenlabs.io/v1"
        # Sarah voice - warm, professional British female
        self.default_voice_id = "EXAVITQu4vr4xnSDxMaL"
        self.default_model = "eleven_turbo_v2_5"

        # Voice settings optimized for clarity
        self.voice_settings = {
            "stability": 0.71,
            "similarity_boost": 0.85,
            "style": 0.35,
            "use_speaker_boost": True,
        }

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """
        Synthesize speech from text.

        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID (default: Sarah)
            model_id: Model to use (default: turbo v2.5)
            output_format: Audio format (mp3_44100_128, pcm_16000, etc.)

        Returns:
            Audio bytes
        """
        voice_id = voice_id or self.default_voice_id
        model_id = model_id or self.default_model

        url = f"{self.base_url}/text-to-speech/{voice_id}"

        params = {"output_format": output_format}

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": self.voice_settings,
        }

        logger.info(
            "elevenlabs_synthesis_started",
            text_length=len(text),
            voice_id=voice_id,
            model_id=model_id,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                audio_data = response.content

            logger.info(
                "elevenlabs_synthesis_complete",
                audio_size=len(audio_data),
                output_format=output_format,
            )

            return audio_data

        except httpx.HTTPStatusError as e:
            logger.error(
                "elevenlabs_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error("elevenlabs_synthesis_error", error=str(e))
            raise

    async def synthesize_with_timestamps(
        self,
        text: str,
        voice_id: str | None = None,
    ) -> dict:
        """
        Synthesize speech with word-level timestamps.

        Useful for syncing audio with visual elements.
        """
        voice_id = voice_id or self.default_voice_id

        url = f"{self.base_url}/text-to-speech/{voice_id}/with-timestamps"

        payload = {
            "text": text,
            "model_id": self.default_model,
            "voice_settings": self.voice_settings,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error("elevenlabs_timestamp_synthesis_error", error=str(e))
            raise

    async def generate_voice_note(self, text: str) -> str:
        """
        Generate a voice note and return URL.

        This uploads the audio to S3 and returns a public URL
        that can be sent via WhatsApp.
        """
        # Import here to avoid circular dependency
        from services.storage_service import storage_service

        # Generate audio
        audio_data = await self.synthesize(text, output_format="mp3_44100_128")

        # Upload to S3 and get URL
        import uuid

        filename = f"voice-notes/{uuid.uuid4()}.mp3"
        url = await storage_service.upload_audio(audio_data, filename)

        logger.info("voice_note_generated", url=url, size=len(audio_data))

        return url

    async def get_voices(self) -> list[dict]:
        """Get list of available voices."""
        url = f"{self.base_url}/voices"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()
                return data.get("voices", [])
        except Exception as e:
            logger.error("elevenlabs_get_voices_error", error=str(e))
            return []

    async def get_voice_settings(self, voice_id: str) -> dict:
        """Get settings for a specific voice."""
        url = f"{self.base_url}/voices/{voice_id}/settings"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("elevenlabs_get_settings_error", error=str(e))
            return {}

    async def get_user_info(self) -> dict:
        """Get current user/subscription info."""
        url = f"{self.base_url}/user"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("elevenlabs_get_user_error", error=str(e))
            return {}


# Singleton instance
elevenlabs_service = ElevenLabsService()
