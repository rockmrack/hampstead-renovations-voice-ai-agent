"""
Conversation service for managing chat history and context.
Uses Redis for caching and PostgreSQL for persistence.
"""

from datetime import datetime

import structlog
from config import settings
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


# Singleton instance
conversation_service = ConversationService()
