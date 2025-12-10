"""
Deepgram speech-to-text service.
Handles audio transcription with Nova-2 model optimized for UK English.
"""

import httpx
import structlog
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class DeepgramService:
    """Service for Deepgram speech-to-text transcription."""

    def __init__(self):
        self.api_key = settings.deepgram_api_key
        self.base_url = "https://api.deepgram.com/v1"
        self.default_options = {
            "model": "nova-2",
            "language": "en-GB",
            "smart_format": "true",
            "punctuate": "true",
            "diarize": "false",
            "utterances": "false",
            "detect_language": "false",
            "filler_words": "false",
            "profanity_filter": "false",
        }

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/ogg",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def transcribe(
        self,
        audio_data: bytes,
        content_type: str = "audio/ogg",
        options: dict | None = None,
    ) -> str:
        """
        Transcribe audio to text using Deepgram Nova-2.

        Args:
            audio_data: Raw audio bytes
            content_type: MIME type of audio (audio/ogg, audio/wav, etc.)
            options: Override default transcription options

        Returns:
            Transcribed text
        """
        # Merge options
        params = {**self.default_options, **(options or {})}

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
        }

        url = f"{self.base_url}/listen"

        logger.info(
            "deepgram_transcription_started",
            audio_size=len(audio_data),
            content_type=content_type,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    headers=headers,
                    content=audio_data,
                )
                response.raise_for_status()
                result = response.json()

            # Extract transcript
            transcript = ""
            channels = result.get("results", {}).get("channels", [])
            if channels:
                alternatives = channels[0].get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")

            # Get metadata
            metadata = result.get("metadata", {})
            duration = metadata.get("duration", 0)
            confidence = alternatives[0].get("confidence", 0) if alternatives else 0

            logger.info(
                "deepgram_transcription_complete",
                transcript_length=len(transcript),
                duration_seconds=duration,
                confidence=confidence,
            )

            return transcript

        except httpx.HTTPStatusError as e:
            logger.error(
                "deepgram_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error("deepgram_transcription_error", error=str(e))
            raise

    async def transcribe_url(self, audio_url: str, options: dict | None = None) -> str:
        """
        Transcribe audio from a URL.

        Args:
            audio_url: URL of the audio file
            options: Override default transcription options

        Returns:
            Transcribed text
        """
        params = {**self.default_options, **(options or {})}

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/listen"
        payload = {"url": audio_url}

        logger.info("deepgram_url_transcription_started", audio_url=audio_url)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

            transcript = ""
            channels = result.get("results", {}).get("channels", [])
            if channels:
                alternatives = channels[0].get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")

            logger.info(
                "deepgram_url_transcription_complete",
                transcript_length=len(transcript),
            )

            return transcript

        except Exception as e:
            logger.error("deepgram_url_transcription_error", error=str(e))
            raise

    async def get_supported_languages(self) -> list[dict]:
        """Get list of supported languages from Deepgram."""
        return [
            {"code": "en-GB", "name": "English (UK)", "model": "nova-2"},
            {"code": "en-US", "name": "English (US)", "model": "nova-2"},
            {"code": "es", "name": "Spanish", "model": "nova-2"},
            {"code": "fr", "name": "French", "model": "nova-2"},
            {"code": "de", "name": "German", "model": "nova-2"},
            {"code": "it", "name": "Italian", "model": "nova-2"},
            {"code": "pt", "name": "Portuguese", "model": "nova-2"},
            {"code": "nl", "name": "Dutch", "model": "nova-2"},
        ]


# Singleton instance
deepgram_service = DeepgramService()
