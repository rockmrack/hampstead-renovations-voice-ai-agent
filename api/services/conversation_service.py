"""
Conversation service for managing chat history and context.
Uses Redis for caching and PostgreSQL for persistence.
"""

from datetime import datetime

import structlog
from config import settings
from models.conversation import SentimentAnalysis  # noqa: I001
from redis import asyncio as aioredis

logger = structlog.get_logger(__name__)


class ConversationService:
    """Service for managing conversation state and history."""

    def __init__(self):
        self.redis_url = settings.redis_url
        self.cache_ttl = settings.redis_conversation_ttl
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_conversation_key(self, phone: str, channel: str = "whatsapp") -> str:
        """Generate Redis key for conversation."""
        phone_clean = phone.replace("+", "").replace(" ", "")
        return f"conversation:{channel}:{phone_clean}"

    def _get_context_key(self, phone: str) -> str:
        """Generate Redis key for conversation context."""
        phone_clean = phone.replace("+", "").replace(" ", "")
        return f"context:{phone_clean}"

    async def get_conversation_history(
        self,
        phone: str,
        channel: str = "whatsapp",
        max_messages: int = 10,
    ) -> str:
        """
        Get recent conversation history for context.

        Args:
            phone: Customer phone number
            channel: Communication channel
            max_messages: Maximum messages to return

        Returns:
            Formatted conversation history string
        """
        try:
            redis = await self._get_redis()
            key = self._get_conversation_key(phone, channel)

            # Get recent messages from list
            messages = await redis.lrange(key, 0, max_messages * 2 - 1)

            if not messages:
                return ""

            # Format messages
            history_lines = []
            for msg in reversed(messages):
                history_lines.append(msg)

            return "\n".join(history_lines)

        except Exception as e:
            logger.error("conversation_history_error", error=str(e), phone=phone)
            return ""

    async def add_message(
        self,
        phone: str,
        role: str,
        content: str,
        channel: str = "whatsapp",
    ) -> None:
        """
        Add a message to conversation history.

        Args:
            phone: Customer phone number
            role: 'customer' or 'agent'
            content: Message content
            channel: Communication channel
        """
        try:
            redis = await self._get_redis()
            key = self._get_conversation_key(phone, channel)

            # Format message
            timestamp = datetime.utcnow().strftime("%H:%M")
            formatted = f"[{timestamp}] {role.title()}: {content}"

            # Add to list (newest at front)
            await redis.lpush(key, formatted)

            # Trim to keep only recent messages
            await redis.ltrim(key, 0, 19)  # Keep last 20 messages

            # Set expiry
            await redis.expire(key, self.cache_ttl)

        except Exception as e:
            logger.error("add_message_error", error=str(e), phone=phone)

    async def log_message(
        self,
        phone: str,
        direction: str,
        content: str,
        response: str,
        channel: str = "whatsapp",
    ) -> None:
        """
        Log a message exchange to history.

        Args:
            phone: Customer phone number
            direction: 'inbound' or 'outbound'
            content: Customer message
            response: Agent response
            channel: Communication channel
        """
        try:
            # Add customer message
            await self.add_message(phone, "Customer", content, channel)

            # Add agent response
            await self.add_message(phone, "Agent", response, channel)

            logger.debug(
                "message_logged",
                phone=phone,
                channel=channel,
                direction=direction,
            )

        except Exception as e:
            logger.error("log_message_error", error=str(e))

    async def get_context(self, phone: str) -> dict:
        """
        Get stored context for a conversation.

        Returns extracted information like name, project type, etc.
        """
        try:
            redis = await self._get_redis()
            key = self._get_context_key(phone)

            context = await redis.hgetall(key)
            return context or {}

        except Exception as e:
            logger.error("get_context_error", error=str(e))
            return {}

    async def update_context(self, phone: str, updates: dict) -> None:
        """
        Update conversation context with new information.

        Args:
            phone: Customer phone number
            updates: Dict of context key-value pairs to update
        """
        try:
            redis = await self._get_redis()
            key = self._get_context_key(phone)

            if updates:
                await redis.hset(key, mapping=updates)
                await redis.expire(key, self.cache_ttl)

        except Exception as e:
            logger.error("update_context_error", error=str(e))

    async def clear_conversation(self, phone: str, channel: str = "whatsapp") -> None:
        """Clear conversation history for a phone number."""
        try:
            redis = await self._get_redis()
            conv_key = self._get_conversation_key(phone, channel)
            ctx_key = self._get_context_key(phone)

            await redis.delete(conv_key, ctx_key)

            logger.info("conversation_cleared", phone=phone)

        except Exception as e:
            logger.error("clear_conversation_error", error=str(e))

    async def get_active_conversations(self) -> list[dict]:
        """Get list of currently active conversations."""
        try:
            redis = await self._get_redis()

            # Find all conversation keys
            keys = await redis.keys("conversation:*")

            conversations = []
            for key in keys:
                parts = key.split(":")
                if len(parts) >= 3:
                    channel = parts[1]
                    phone = parts[2]

                    # Get most recent message
                    recent = await redis.lrange(key, 0, 0)

                    conversations.append(
                        {
                            "phone": phone,
                            "channel": channel,
                            "last_message": recent[0] if recent else None,
                        }
                    )

            return conversations

        except Exception as e:
            logger.error("get_active_conversations_error", error=str(e))
            return []

    async def get_conversation_stats(self) -> dict:
        """Get conversation statistics."""
        try:
            redis = await self._get_redis()

            whatsapp_keys = await redis.keys("conversation:whatsapp:*")
            phone_keys = await redis.keys("conversation:phone:*")

            return {
                "active_whatsapp": len(whatsapp_keys),
                "active_phone": len(phone_keys),
                "total_active": len(whatsapp_keys) + len(phone_keys),
            }

        except Exception as e:
            logger.error("conversation_stats_error", error=str(e))
            return {"active_whatsapp": 0, "active_phone": 0, "total_active": 0}

    async def analyse_sentiment(
        self,
        message: str,
        conversation_history: list[dict] | None = None,  # noqa: ARG002 - Reserved for context-aware analysis
    ) -> SentimentAnalysis:
        """
        Analyse customer sentiment from latest message.

        Args:
            message: Latest customer message
            conversation_history: Recent conversation messages (reserved for future use)

        Returns:
            SentimentAnalysis with sentiment and signals
        """
        message_lower = message.lower()

        # Price shock indicators
        price_shock_signals = [
            "how much?!",
            "that much",
            "that's expensive",
            "can't afford",
            "out of my budget",
            "way more than",
            "wasn't expecting",
            "seriously?",
            "you're joking",
        ]
        if any(signal in message_lower for signal in price_shock_signals):
            return SentimentAnalysis(
                sentiment="price_shocked",
                confidence=0.8,
                signals=["price_reaction_detected"],
                requires_review=True,
            )

        # Frustration/anger indicators
        frustration_signals = [
            "frustrated",
            "annoying",
            "ridiculous",
            "waste of time",
            "not helpful",
            "useless",
            "terrible",
            "awful",
            "pathetic",
        ]
        if any(signal in message_lower for signal in frustration_signals):
            return SentimentAnalysis(
                sentiment="frustrated",
                confidence=0.85,
                signals=["frustration_keywords"],
                requires_review=True,
            )

        # Anger escalation
        anger_signals = [
            "furious",
            "disgusted",
            "appalled",
            "sue",
            "lawyer",
            "report you",
        ]
        if any(signal in message_lower for signal in anger_signals):
            return SentimentAnalysis(
                sentiment="angry",
                confidence=0.9,
                signals=["anger_escalation"],
                requires_review=True,
            )

        # Positive indicators
        positive_signals = [
            "thank you",
            "thanks",
            "great",
            "excellent",
            "perfect",
            "brilliant",
            "wonderful",
            "amazing",
            "love it",
            "sounds good",
        ]
        if any(signal in message_lower for signal in positive_signals):
            return SentimentAnalysis(
                sentiment="positive",
                confidence=0.75,
                signals=["positive_language"],
                requires_review=False,
            )

        # Concerned indicators
        concerned_signals = [
            "worried",
            "concerned",
            "not sure",
            "hesitant",
            "nervous",
            "uncertain",
        ]
        if any(signal in message_lower for signal in concerned_signals):
            return SentimentAnalysis(
                sentiment="concerned",
                confidence=0.7,
                signals=["concern_detected"],
                requires_review=False,
            )

        # Default to neutral
        return SentimentAnalysis(
            sentiment="neutral",
            confidence=0.5,
            signals=[],
            requires_review=False,
        )

    async def flag_for_review(
        self,
        conversation_id: str,
        phone: str,
        sentiment_analysis: SentimentAnalysis,
        customer_name: str | None = None,
    ) -> str:
        """
        Flag a conversation for manual review.

        Args:
            conversation_id: Unique conversation identifier
            phone: Customer phone number
            sentiment_analysis: Sentiment analysis result
            customer_name: Optional customer name

        Returns:
            Flag ID
        """
        import uuid

        redis = await self._get_redis()
        flag_id = str(uuid.uuid4())[:8]

        # Determine urgency based on sentiment
        urgency_map = {
            "angry": "urgent",
            "frustrated": "high",
            "price_shocked": "high",
            "concerned": "normal",
        }
        urgency = urgency_map.get(sentiment_analysis.sentiment, "normal")

        flag_data = {
            "conversation_id": conversation_id,
            "phone": phone,
            "customer_name": customer_name or "Unknown",
            "flag_reason": f"Sentiment: {sentiment_analysis.sentiment}",
            "sentiment": sentiment_analysis.sentiment,
            "signals": ",".join(sentiment_analysis.signals),
            "confidence": str(sentiment_analysis.confidence),
            "urgency": urgency,
            "created_at": datetime.utcnow().isoformat(),
            "reviewed": "false",
        }

        await redis.hset(f"flag:{flag_id}", mapping=flag_data)
        await redis.expire(f"flag:{flag_id}", 86400 * 7)  # Keep for 7 days

        # Add to flags list for easy retrieval
        await redis.lpush("flags:pending", flag_id)
        await redis.ltrim("flags:pending", 0, 99)  # Keep last 100 flags

        logger.info(
            "conversation_flagged",
            flag_id=flag_id,
            phone=phone,
            sentiment=sentiment_analysis.sentiment,
            urgency=urgency,
        )

        return flag_id

    async def get_pending_flags(self, limit: int = 20) -> list[dict]:
        """
        Get list of pending review flags.

        Args:
            limit: Maximum flags to return

        Returns:
            List of flag dictionaries
        """
        try:
            redis = await self._get_redis()
            flag_ids = await redis.lrange("flags:pending", 0, limit - 1)

            flags = []
            for flag_id in flag_ids:
                flag_data = await redis.hgetall(f"flag:{flag_id}")
                if flag_data and flag_data.get("reviewed") == "false":
                    flag_data["id"] = flag_id
                    flags.append(flag_data)

            return flags

        except Exception as e:
            logger.error("get_pending_flags_error", error=str(e))
            return []

    async def mark_flag_reviewed(self, flag_id: str, notes: str | None = None) -> bool:
        """
        Mark a flag as reviewed.

        Args:
            flag_id: Flag ID to mark
            notes: Optional review notes

        Returns:
            True if successfully marked
        """
        try:
            redis = await self._get_redis()
            key = f"flag:{flag_id}"

            exists = await redis.exists(key)
            if not exists:
                return False

            updates = {
                "reviewed": "true",
                "reviewed_at": datetime.utcnow().isoformat(),
            }
            if notes:
                updates["notes"] = notes

            await redis.hset(key, mapping=updates)

            logger.info("flag_marked_reviewed", flag_id=flag_id)
            return True

        except Exception as e:
            logger.error("mark_flag_reviewed_error", error=str(e), flag_id=flag_id)
            return False

    async def get_full_transcript(
        self,
        phone: str,
        channel: str = "whatsapp",
    ) -> list[dict]:
        """
        Get full conversation transcript as structured list.

        Args:
            phone: Customer phone number
            channel: Communication channel

        Returns:
            List of message dicts with role and content
        """
        try:
            redis = await self._get_redis()
            key = self._get_conversation_key(phone, channel)

            messages = await redis.lrange(key, 0, -1)

            transcript = []
            for msg in reversed(messages):
                # Parse formatted message: [HH:MM] Role: Content
                if "] " in msg and ": " in msg:
                    role_content = msg.split("] ", 1)[1]
                    if ": " in role_content:
                        role, content = role_content.split(": ", 1)
                        transcript.append(
                            {
                                "role": role.lower(),
                                "content": content,
                            }
                        )

            return transcript

        except Exception as e:
            logger.error("get_full_transcript_error", error=str(e), phone=phone)
            return []

    async def set_status(self, phone: str, status: str) -> None:
        """
        Set conversation status.

        Args:
            phone: Customer phone number
            status: Status string (active, pending_handoff, closed, etc.)
        """
        await self.update_context(phone, {"status": status})


# Singleton instance
conversation_service = ConversationService()
