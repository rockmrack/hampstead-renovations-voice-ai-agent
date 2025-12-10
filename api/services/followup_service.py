"""
Follow-up service for automated lead re-engagement.
Re-engages leads who've gone quiet after 7 days with personalised messages.
"""

import asyncio
from datetime import datetime

import anthropic
import structlog
from config import settings

logger = structlog.get_logger()


class FollowupService:
    """Service for managing automated follow-up messages to stale leads."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"
        self._redis = None
        self._db = None

    def _get_redis(self):
        """Lazy load Redis connection."""
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(settings.redis_url)
        return self._redis

    async def get_stale_leads(self, days: int = 7) -> list[dict]:
        """
        Get leads with no activity in X days who haven't been followed up.

        Args:
            days: Number of days of inactivity

        Returns:
            List of lead dictionaries
        """
        redis = self._get_redis()

        # Get all lead keys
        lead_keys = await redis.keys("lead:*")
        stale_leads = []
        now = datetime.now()

        for key in lead_keys:
            lead_data = await redis.hgetall(key)
            if not lead_data:
                continue

            # Decode bytes to strings
            lead = {k.decode(): v.decode() for k, v in lead_data.items()}

            # Check last message time
            last_message = lead.get("last_message_at")
            if not last_message:
                continue

            last_message_dt = datetime.fromisoformat(last_message)
            days_since = (now - last_message_dt).days

            # Check criteria
            if days_since < days or days_since > 30:
                continue

            status = lead.get("status", "active")
            if status in ("converted", "lost", "unsubscribed"):
                continue

            followup_count = int(lead.get("followup_count", 0))
            if followup_count >= 3:
                continue

            last_followup = lead.get("last_followup_at")
            if last_followup:
                last_followup_dt = datetime.fromisoformat(last_followup)
                days_since_followup = (now - last_followup_dt).days
                if days_since_followup < 5:
                    continue

            lead["id"] = key.decode().split(":")[-1]
            stale_leads.append(lead)

        # Sort by lead score descending
        stale_leads.sort(key=lambda x: int(x.get("lead_score", 0)), reverse=True)

        return stale_leads[:20]

    async def generate_followup_message(self, lead: dict) -> str:
        """
        Generate personalised follow-up message based on conversation history.

        Args:
            lead: Lead data dictionary

        Returns:
            Generated follow-up message
        """
        name = lead.get("name", "there")
        project_type = lead.get("project_type", "home renovation")
        last_message_at = lead.get("last_message_at", "a while ago")
        last_summary = lead.get("last_summary", "General enquiry")
        followup_count = int(lead.get("followup_count", 0)) + 1

        prompt = f"""Generate a warm, non-pushy follow-up WhatsApp message for this lead.

CONTEXT:
- Name: {name}
- Interested in: {project_type}
- Last contact: {last_message_at}
- Previous conversation summary: {last_summary}
- Follow-up number: {followup_count}

RULES:
- Keep it under 50 words
- Don't be salesy or pushy
- Reference something specific from their enquiry if possible
- End with an easy question (not demanding a call/meeting)
- Sound like a human, not a bot
- If this is follow-up #2 or #3, acknowledge you've reached out before
- Use British English

EXAMPLES OF GOOD FOLLOW-UPS:
"Hi [name], hope you're well! Just checking if you had any more questions about the loft conversion we discussed? No rush at all - just didn't want you to think we'd forgotten about you"

"Hi [name], quick thought - I was at a kitchen project in Hampstead yesterday and thought of your extension plans. Still mulling it over or have you moved forward with someone else? Either way, happy to help if needed."

Generate ONE follow-up message (no quotes, just the message text):"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )

            message = response.content[0].text.strip()
            # Remove any surrounding quotes
            message = message.strip("\"'")

            logger.info("followup_message_generated", lead_id=lead.get("id"), message=message[:50])
            return message

        except Exception as e:
            logger.error("followup_generation_error", error=str(e))
            # Fallback message
            return f"Hi {name}, hope you're doing well! Just wanted to check in about your {project_type} project. Any questions I can help with?"

    async def send_followup(self, lead: dict, whatsapp_service) -> bool:
        """
        Send follow-up message and update lead record.

        Args:
            lead: Lead data dictionary
            whatsapp_service: WhatsApp service instance

        Returns:
            True if sent successfully
        """
        message = await self.generate_followup_message(lead)
        phone = lead.get("phone")

        if not phone:
            logger.warning("followup_no_phone", lead_id=lead.get("id"))
            return False

        # Send via WhatsApp
        success = await whatsapp_service.send_message(phone, message)

        if success:
            redis = self._get_redis()
            lead_key = f"lead:{lead.get('id')}"

            # Update lead record
            await redis.hincrby(lead_key, "followup_count", 1)
            await redis.hset(lead_key, "last_followup_at", datetime.now().isoformat())

            # Log the interaction
            log_key = f"message_log:{phone}:{datetime.now().timestamp()}"
            await redis.hset(
                log_key,
                mapping={
                    "lead_id": lead.get("id"),
                    "direction": "outbound",
                    "content": message,
                    "channel": "whatsapp",
                    "message_type": "followup",
                    "created_at": datetime.now().isoformat(),
                },
            )
            await redis.expire(log_key, 86400 * 90)  # Keep for 90 days

            logger.info("followup_sent", lead_id=lead.get("id"), phone=phone)

        return success

    async def run_daily_followups(self, whatsapp_service) -> dict:
        """
        Main job - run daily follow-ups.

        Args:
            whatsapp_service: WhatsApp service instance

        Returns:
            Results dictionary with counts
        """
        stale_leads = await self.get_stale_leads(days=7)

        results = {"sent": 0, "failed": 0, "skipped": 0}

        for lead in stale_leads:
            # Skip if lead score too low
            lead_score = int(lead.get("lead_score", 0))
            if lead_score < 30:
                results["skipped"] += 1
                logger.info("followup_skipped_low_score", lead_id=lead.get("id"), score=lead_score)
                continue

            success = await self.send_followup(lead, whatsapp_service)

            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1

            # Rate limit - don't spam
            await asyncio.sleep(5)

        logger.info("daily_followups_complete", **results)
        return results


# Singleton instance
followup_service = FollowupService()
