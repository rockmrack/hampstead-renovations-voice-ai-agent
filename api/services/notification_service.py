"""
Notification service for alerts and escalations.
Handles Slack, Email, and SMS notifications.
"""

from datetime import datetime
from typing import Optional

import httpx
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class NotificationService:
    """Service for sending notifications and alerts."""

    def __init__(self):
        self.slack_webhook_url = settings.slack_webhook_url
        self.slack_channel = settings.slack_channel
        self.ross_mobile = settings.ross_mobile_number
        self.ross_email = settings.ross_email

    async def notify_slack(
        self,
        message: str,
        channel: Optional[str] = None,
        username: str = "Voice Agent",
        icon_emoji: str = ":robot_face:",
        attachments: Optional[list] = None,
    ) -> bool:
        """
        Send notification to Slack channel.
        
        Args:
            message: Main message text
            channel: Override default channel
            username: Bot username
            icon_emoji: Emoji for bot avatar
            attachments: Rich message attachments
        """
        if not self.slack_webhook_url:
            logger.warning("slack_webhook_not_configured")
            return False

        payload = {
            "channel": channel or self.slack_channel,
            "username": username,
            "icon_emoji": icon_emoji,
            "text": message,
        }

        if attachments:
            payload["attachments"] = attachments

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.slack_webhook_url, json=payload)
                response.raise_for_status()

            logger.info("slack_notification_sent", channel=channel or self.slack_channel)
            return True

        except Exception as e:
            logger.error("slack_notification_error", error=str(e))
            return False

    async def notify_escalation(
        self,
        phone: str,
        reason: str,
        conversation: str,
        urgency: str = "same-day",
    ) -> None:
        """
        Send escalation notification for upset/complex customer.
        
        Args:
            phone: Customer phone number
            reason: Reason for escalation
            conversation: Recent conversation context
            urgency: 'immediate', 'same-day', 'next-day'
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        # Determine emoji based on urgency
        urgency_emoji = {
            "immediate": "🚨",
            "same-day": "⚠️",
            "next-day": "📋",
        }.get(urgency, "📋")

        slack_message = f"{urgency_emoji} *Escalation Required*"
        
        attachments = [
            {
                "color": "danger" if urgency == "immediate" else "warning",
                "fields": [
                    {"title": "Customer Phone", "value": phone, "short": True},
                    {"title": "Urgency", "value": urgency.replace("-", " ").title(), "short": True},
                    {"title": "Reason", "value": reason, "short": False},
                    {"title": "Conversation Snippet", "value": conversation[:500], "short": False},
                ],
                "footer": f"Voice Agent Escalation | {timestamp}",
            }
        ]

        await self.notify_slack(
            message=slack_message,
            attachments=attachments,
            icon_emoji=":warning:",
        )

        # For immediate escalations, also send SMS to Ross
        if urgency == "immediate":
            await self.send_sms_alert(
                f"URGENT: Customer {phone} needs immediate callback. Reason: {reason}"
            )

        logger.info(
            "escalation_notification_sent",
            phone=phone,
            urgency=urgency,
            reason=reason,
        )

    async def notify_transfer_request(
        self,
        customer_phone: str,
        reason: str,
        urgency: str = "same-day",
    ) -> None:
        """
        Notify about a call transfer/callback request.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        slack_message = "📞 *Callback Request*"
        
        attachments = [
            {
                "color": "good" if urgency != "immediate" else "warning",
                "fields": [
                    {"title": "Customer Phone", "value": customer_phone, "short": True},
                    {"title": "Callback Timing", "value": urgency.replace("-", " ").title(), "short": True},
                    {"title": "Reason", "value": reason, "short": False},
                ],
                "footer": f"Voice Agent | {timestamp}",
            }
        ]

        await self.notify_slack(
            message=slack_message,
            attachments=attachments,
            icon_emoji=":telephone_receiver:",
        )

        logger.info("transfer_request_notification_sent", phone=customer_phone)

    async def notify_new_lead(
        self,
        phone: str,
        name: Optional[str],
        project_type: Optional[str],
        lead_score: Optional[int],
        lead_tier: Optional[str],
        source: str = "whatsapp",
    ) -> None:
        """
        Notify about a new qualified lead.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        # Color based on lead tier
        tier_colors = {
            "hot": "good",
            "warm": "warning",
            "cold": "#439FE0",
        }
        
        tier_emoji = {
            "hot": "🔥",
            "warm": "👍",
            "cold": "❄️",
        }
        
        emoji = tier_emoji.get(lead_tier, "📋")
        color = tier_colors.get(lead_tier, "#808080")

        slack_message = f"{emoji} *New Lead*"
        
        attachments = [
            {
                "color": color,
                "fields": [
                    {"title": "Name", "value": name or "Not provided", "short": True},
                    {"title": "Phone", "value": phone, "short": True},
                    {"title": "Project Type", "value": project_type or "Not specified", "short": True},
                    {"title": "Lead Score", "value": str(lead_score) if lead_score else "N/A", "short": True},
                    {"title": "Lead Tier", "value": (lead_tier or "unqualified").title(), "short": True},
                    {"title": "Source", "value": source.title(), "short": True},
                ],
                "footer": f"Voice Agent | {timestamp}",
            }
        ]

        await self.notify_slack(
            message=slack_message,
            attachments=attachments,
            icon_emoji=":star:",
        )

        logger.info(
            "new_lead_notification_sent",
            phone=phone,
            lead_tier=lead_tier,
            lead_score=lead_score,
        )

    async def notify_booking_created(
        self,
        customer_name: str,
        phone: str,
        address: str,
        date: str,
        time: str,
        project_type: Optional[str] = None,
    ) -> None:
        """
        Notify about a new survey booking.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        slack_message = "📅 *New Survey Booking*"
        
        attachments = [
            {
                "color": "good",
                "fields": [
                    {"title": "Customer", "value": customer_name, "short": True},
                    {"title": "Phone", "value": phone, "short": True},
                    {"title": "Date", "value": date, "short": True},
                    {"title": "Time", "value": time, "short": True},
                    {"title": "Address", "value": address, "short": False},
                    {"title": "Project Type", "value": project_type or "General enquiry", "short": True},
                ],
                "footer": f"Voice Agent | {timestamp}",
            }
        ]

        await self.notify_slack(
            message=slack_message,
            attachments=attachments,
            icon_emoji=":calendar:",
        )

        logger.info(
            "booking_notification_sent",
            customer=customer_name,
            date=date,
            time=time,
        )

    async def send_sms_alert(self, message: str) -> bool:
        """
        Send SMS alert to Ross for urgent matters.
        Uses Twilio if configured.
        """
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning("twilio_not_configured")
            return False

        from twilio.rest import Client

        try:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            
            sms = client.messages.create(
                body=message[:160],  # SMS limit
                from_=settings.twilio_phone_number,
                to=self.ross_mobile,
            )

            logger.info("sms_alert_sent", sid=sms.sid)
            return True

        except Exception as e:
            logger.error("sms_alert_error", error=str(e))
            return False

    async def send_email_alert(
        self,
        subject: str,
        body: str,
        to_email: Optional[str] = None,
    ) -> bool:
        """
        Send email alert (for less urgent notifications).
        """
        # This would typically use SendGrid, AWS SES, or similar
        # For now, just log and return
        logger.info(
            "email_alert_queued",
            subject=subject,
            to=to_email or self.ross_email,
        )
        return True

    async def notify_daily_summary(self, stats: dict) -> None:
        """
        Send daily summary notification.
        """
        slack_message = "📊 *Daily Voice Agent Summary*"
        
        attachments = [
            {
                "color": "#439FE0",
                "fields": [
                    {"title": "Total Conversations", "value": str(stats.get("total_conversations", 0)), "short": True},
                    {"title": "WhatsApp Messages", "value": str(stats.get("whatsapp_messages", 0)), "short": True},
                    {"title": "Phone Calls", "value": str(stats.get("phone_calls", 0)), "short": True},
                    {"title": "Bookings Made", "value": str(stats.get("bookings", 0)), "short": True},
                    {"title": "Hot Leads", "value": str(stats.get("hot_leads", 0)), "short": True},
                    {"title": "Escalations", "value": str(stats.get("escalations", 0)), "short": True},
                ],
                "footer": datetime.utcnow().strftime("Report for %Y-%m-%d"),
            }
        ]

        await self.notify_slack(
            message=slack_message,
            attachments=attachments,
            icon_emoji=":bar_chart:",
        )


# Singleton instance
notification_service = NotificationService()
