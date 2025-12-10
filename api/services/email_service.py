"""
Email service for sending transactional emails via SendGrid.
Used for post-call summaries and notifications.
"""

import httpx
import structlog
from config import settings

logger = structlog.get_logger()


class EmailService:
    """Service for sending emails via SendGrid API."""

    def __init__(self) -> None:
        self.api_key = settings.sendgrid_api_key if hasattr(settings, "sendgrid_api_key") else ""
        self.from_email = "ai@hampsteadrenovations.co.uk"
        self.from_name = "Hampstead AI"
        self.api_url = "https://api.sendgrid.com/v3/mail/send"

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        """
        Send an email via SendGrid.

        Args:
            to: Recipient email address
            subject: Email subject line
            body: Plain text body
            html_body: Optional HTML body

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.api_key:
            logger.warning("email_not_sent_no_api_key", to=to, subject=subject)
            return False

        content = [{"type": "text/plain", "value": body}]
        if html_body:
            content.append({"type": "text/html", "value": html_body})

        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_email, "name": self.from_name},
            "subject": subject,
            "content": content,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code in (200, 202):
                    logger.info("email_sent", to=to, subject=subject)
                    return True
                else:
                    logger.error(
                        "email_send_failed",
                        to=to,
                        subject=subject,
                        status=response.status_code,
                        response=response.text,
                    )
                    return False

        except Exception as e:
            logger.error("email_send_error", to=to, subject=subject, error=str(e))
            return False

    async def send_to_ross(self, subject: str, body: str, html_body: str | None = None) -> bool:
        """Send email to Ross (business owner)."""
        return await self.send(settings.ross_email, subject, body, html_body)


# Singleton instance
email_service = EmailService()
