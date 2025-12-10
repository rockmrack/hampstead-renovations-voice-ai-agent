"""
Summary service for generating post-conversation summaries.
Auto-generates and emails 5-line summaries after every conversation.
"""

import json
from datetime import datetime

import anthropic
import structlog
from config import settings
from models.conversation import ConversationSummary

from services.email_service import email_service

logger = structlog.get_logger()


class SummaryService:
    """Service for generating and sending conversation summaries."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"
        self.ross_email = settings.ross_email

    async def generate_summary(
        self,
        transcript: list[dict],
        channel: str,
        contact_info: str,
    ) -> ConversationSummary:
        """
        Generate a summary from conversation transcript.

        Args:
            transcript: List of message dicts with 'role' and 'content'
            channel: Communication channel (whatsapp, phone, voice_note)
            contact_info: Customer phone number or identifier

        Returns:
            ConversationSummary with extracted information
        """
        transcript_text = "\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in transcript]
        )

        schema = ConversationSummary.model_json_schema()
        prompt = f"""Summarise this {channel} conversation for the business owner.

TRANSCRIPT:
{transcript_text}

Extract:
1. Customer name (if mentioned)
2. Project type they're interested in
3. Budget signals (any numbers mentioned, or reactions to pricing)
4. Key objections or concerns raised
5. Overall sentiment (positive/neutral/concerned/negative)
6. Recommended next action
7. Is this a hot lead (genuine interest + realistic budget + ready timeline)?

Write a 5-line plain English summary suitable for a quick email scan.

Return as JSON matching this schema: {json.dumps(schema)}

IMPORTANT: Return valid JSON only, no other text."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            result = json.loads(response.content[0].text)
            result["phone_or_contact"] = contact_info

            logger.info(
                "summary_generated",
                channel=channel,
                contact=contact_info,
                hot_lead=result.get("hot_lead", False),
            )
            return ConversationSummary(**result)

        except json.JSONDecodeError as e:
            logger.error("summary_json_error", error=str(e))
            return ConversationSummary(
                phone_or_contact=contact_info,
                sentiment="neutral",
                next_action="Review conversation manually",
                hot_lead=False,
                summary_text="Unable to generate automated summary. Please review the transcript.",
            )
        except Exception as e:
            logger.error("summary_generation_error", error=str(e))
            raise

    async def send_summary_email(
        self,
        summary: ConversationSummary,
        channel: str,
    ) -> bool:
        """
        Send summary email to Ross.

        Args:
            summary: Generated conversation summary
            channel: Communication channel

        Returns:
            True if email sent successfully
        """
        subject_emoji = "\U0001f525" if summary.hot_lead else "\U0001f4de"  # fire or phone emoji
        customer_name = summary.customer_name or "Unknown"
        project = summary.project_type or "General enquiry"
        subject = f"{subject_emoji} {channel.title()} Summary: {customer_name} - {project}"

        timestamp = datetime.now().strftime("%d %b %Y %H:%M")
        objections_text = (
            "\n".join([f"  - {obj}" for obj in summary.key_objections])
            if summary.key_objections
            else "  None"
        )
        hot_lead_text = "YES \U0001f525" if summary.hot_lead else "No"

        body = f"""CONVERSATION SUMMARY - {timestamp}

Contact: {summary.phone_or_contact}
Channel: {channel.upper()}
Sentiment: {summary.sentiment.upper()}
Hot Lead: {hot_lead_text}

SUMMARY:
{summary.summary_text}

BUDGET SIGNALS:
{summary.budget_signals or "None detected"}

OBJECTIONS:
{objections_text}

NEXT ACTION:
-> {summary.next_action}

---
Sent by Hampstead AI Voice Agent
"""

        return await email_service.send_to_ross(subject, body)

    async def process_conversation_end(
        self,
        conversation_id: str,
        transcript: list[dict],
        channel: str,
        contact_info: str,
    ) -> ConversationSummary | None:
        """
        Process end of conversation - generate and send summary.

        Args:
            conversation_id: Unique conversation identifier
            transcript: Full conversation transcript
            channel: Communication channel
            contact_info: Customer contact info

        Returns:
            Generated summary or None if skipped
        """
        # Skip very short interactions
        if len(transcript) < 3:
            logger.info(
                "summary_skipped_short_conversation",
                conversation_id=conversation_id,
                message_count=len(transcript),
            )
            return None

        summary = await self.generate_summary(transcript, channel, contact_info)
        await self.send_summary_email(summary, channel)

        return summary


# Singleton instance
summary_service = SummaryService()
