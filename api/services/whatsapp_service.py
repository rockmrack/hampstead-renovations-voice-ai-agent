"""
WhatsApp Business API service via 360dialog.
Handles sending messages, media, and downloading voice notes.
"""

import httpx
import structlog
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class WhatsAppService:
    """Service for WhatsApp Business API via 360dialog."""

    def __init__(self):
        self.api_key = settings.whatsapp_api_key
        self.base_url = settings.whatsapp_api_url
        self.phone_number_id = settings.whatsapp_phone_number_id

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "D360-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def send_text_message(self, to: str, text: str) -> dict:
        """
        Send a text message via WhatsApp.

        Args:
            to: Recipient phone number (E.164 format)
            text: Message text

        Returns:
            API response
        """
        url = f"{self.base_url}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }

        logger.info(
            "whatsapp_sending_text",
            to=to,
            text_length=len(text),
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

            logger.info(
                "whatsapp_text_sent",
                to=to,
                message_id=result.get("messages", [{}])[0].get("id"),
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "whatsapp_send_error",
                status_code=e.response.status_code,
                error=str(e),
                to=to,
            )
            raise
        except Exception as e:
            logger.error("whatsapp_send_error", error=str(e), to=to)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def send_audio_message(self, to: str, audio_url: str) -> dict:
        """
        Send an audio message (voice note) via WhatsApp.

        Args:
            to: Recipient phone number
            audio_url: Public URL of audio file

        Returns:
            API response
        """
        url = f"{self.base_url}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "audio",
            "audio": {"link": audio_url},
        }

        logger.info("whatsapp_sending_audio", to=to, audio_url=audio_url)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

            logger.info(
                "whatsapp_audio_sent",
                to=to,
                message_id=result.get("messages", [{}])[0].get("id"),
            )

            return result

        except Exception as e:
            logger.error("whatsapp_audio_send_error", error=str(e), to=to)
            raise

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_GB",
        components: list | None = None,
    ) -> dict:
        """
        Send a template message (pre-approved by WhatsApp).

        Args:
            to: Recipient phone number
            template_name: Name of approved template
            language_code: Template language
            components: Template variable components

        Returns:
            API response
        """
        url = f"{self.base_url}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }

        if components:
            payload["template"]["components"] = components

        logger.info(
            "whatsapp_sending_template",
            to=to,
            template=template_name,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(
                "whatsapp_template_send_error",
                error=str(e),
                template=template_name,
            )
            raise

    async def send_interactive_buttons(
        self,
        to: str,
        body_text: str,
        buttons: list[dict],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> dict:
        """
        Send interactive message with buttons.

        Args:
            to: Recipient phone number
            body_text: Main message text
            buttons: List of button objects [{id, title}, ...]
            header_text: Optional header
            footer_text: Optional footer
        """
        url = f"{self.base_url}/messages"

        interactive = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]  # Max 3 buttons
                ]
            },
        }

        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error("whatsapp_buttons_send_error", error=str(e))
            raise

    async def download_media(self, media_id: str) -> bytes:
        """
        Download media file from WhatsApp.

        Args:
            media_id: WhatsApp media ID

        Returns:
            Media file bytes
        """
        # First, get the media URL
        url = f"{self.base_url}/media/{media_id}"

        logger.info("whatsapp_downloading_media", media_id=media_id)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Get media URL
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()
                media_info = response.json()
                media_url = media_info.get("url")

                if not media_url:
                    raise ValueError("No media URL returned")

                # Download actual media
                response = await client.get(
                    media_url,
                    headers={"D360-API-KEY": self.api_key},
                )
                response.raise_for_status()

            logger.info(
                "whatsapp_media_downloaded",
                media_id=media_id,
                size=len(response.content),
            )

            return response.content

        except Exception as e:
            logger.error(
                "whatsapp_media_download_error",
                error=str(e),
                media_id=media_id,
            )
            raise

    async def mark_as_read(self, message_id: str) -> dict:
        """Mark a message as read."""
        url = f"{self.base_url}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("whatsapp_mark_read_error", error=str(e))
            return {}

    async def send_reaction(self, message_id: str, to: str, emoji: str) -> dict:
        """Send a reaction to a message."""
        url = f"{self.base_url}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "reaction",
            "reaction": {
                "message_id": message_id,
                "emoji": emoji,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("whatsapp_reaction_error", error=str(e))
            return {}


# Singleton instance
whatsapp_service = WhatsAppService()
