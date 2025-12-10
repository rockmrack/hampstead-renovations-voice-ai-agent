"""
Claude AI service for conversation handling.
Handles all Anthropic Claude API interactions with retry logic and circuit breaker.
"""

import json
from pathlib import Path
from typing import Any

import anthropic
import structlog
from config import settings
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class ClaudeService:
    """Service for Claude AI interactions."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"
        self._system_prompt: str | None = None
        self._knowledge_base: str | None = None

    @property
    def system_prompt(self) -> str:
        """Load and cache system prompt."""
        if self._system_prompt is None:
            prompt_path = Path("prompts/system-prompt.txt")
            if prompt_path.exists():
                self._system_prompt = prompt_path.read_text(encoding="utf-8")
            else:
                self._system_prompt = "You are a helpful assistant for Hampstead Renovations."
        return self._system_prompt

    @property
    def knowledge_base(self) -> str:
        """Load and cache knowledge base."""
        if self._knowledge_base is None:
            kb_dir = Path("knowledge-base")
            knowledge_parts = []
            if kb_dir.exists():
                for file_path in sorted(kb_dir.glob("*.md")):
                    knowledge_parts.append(file_path.read_text(encoding="utf-8"))
            self._knowledge_base = "\n\n---\n\n".join(knowledge_parts)
        return self._knowledge_base

    def _load_prompt(self, prompt_name: str) -> str:
        """Load a specific prompt template."""
        prompt_path = Path(f"prompts/{prompt_name}.txt")
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((anthropic.APIError, anthropic.APIConnectionError)),
    )
    async def _call_claude(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Make a call to Claude API with retry logic."""
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.APIError as e:
            logger.error("claude_api_error", error=str(e), error_type=type(e).__name__)
            raise

    async def generate_whatsapp_response(self, context: dict[str, Any]) -> str:
        """Generate response for WhatsApp text message."""
        prompt_template = self._load_prompt("whatsapp-text-handler")

        system = f"""{self.system_prompt}

KNOWLEDGE BASE:
{self.knowledge_base}

{prompt_template}"""

        # Build conversation history
        history = context.get("conversation_history", "")
        customer_name = context.get("customer_name", "")
        time_of_day = context.get("time_of_day", "day")
        is_existing = context.get("is_existing_contact", False)

        user_message = f"""CONTEXT:
- Customer Name: {customer_name or "Unknown"}
- Time of Day: {time_of_day}
- Existing Contact: {"Yes" if is_existing else "No"}
- Phone: {context.get("phone_number", "")}

CONVERSATION HISTORY:
{history}

CUSTOMER MESSAGE:
{context.get("message", "")}

Generate a natural, helpful response. Keep it concise but warm."""

        messages = [{"role": "user", "content": user_message}]

        response = await self._call_claude(
            messages=messages,
            system=system,
            max_tokens=500,
            temperature=0.7,
        )

        logger.info(
            "whatsapp_response_generated",
            response_length=len(response),
            customer_name=customer_name,
        )

        return response.strip()

    async def generate_voice_response(self, context: dict[str, Any]) -> str:
        """Generate spoken response for voice note (optimized for TTS)."""
        prompt_template = self._load_prompt("voice-note-responder")

        system = f"""{self.system_prompt}

KNOWLEDGE BASE:
{self.knowledge_base}

{prompt_template}

IMPORTANT: Your response will be converted to speech.
- Use natural, spoken language
- Avoid bullet points, formatting, or special characters
- Keep sentences short and clear
- Use conversational phrasing"""

        user_message = f"""CONTEXT:
- Customer Name: {context.get("customer_name", "Unknown")}
- Time of Day: {context.get("time_of_day", "day")}

CONVERSATION HISTORY:
{context.get("conversation_history", "")}

VOICE NOTE TRANSCRIPT:
{context.get("transcript", "")}

Generate a natural spoken response suitable for a voice note reply."""

        messages = [{"role": "user", "content": user_message}]

        response = await self._call_claude(
            messages=messages,
            system=system,
            max_tokens=400,
            temperature=0.7,
        )

        return response.strip()

    async def extract_qualification(self, conversation: str) -> dict[str, Any] | None:
        """Extract lead qualification data from conversation."""
        prompt_template = self._load_prompt("qualification-extractor")

        system = f"""You are a lead qualification extraction system.
Extract structured data from the conversation.

{prompt_template}

Return ONLY valid JSON, no markdown or explanation."""

        user_message = f"""CONVERSATION:
{conversation}

Extract all available qualification data as JSON with this structure:
{{
    "contact": {{
        "name": "string or null",
        "email": "string or null",
        "phone": "string or null",
        "address": "string or null",
        "postcode": "string or null"
    }},
    "project": {{
        "type": "string or null",
        "description": "string or null",
        "timeline": "string or null",
        "budget_range": "string or null",
        "property_type": "string or null"
    }},
    "qualification": {{
        "lead_score": "number 0-100",
        "lead_tier": "hot|warm|cold|unqualified",
        "decision_maker": "boolean or null",
        "urgency": "high|medium|low|unknown",
        "in_service_area": "boolean or null"
    }},
    "next_steps": {{
        "survey_requested": "boolean",
        "callback_requested": "boolean",
        "information_requested": "string or null"
    }}
}}"""

        messages = [{"role": "user", "content": user_message}]

        try:
            response = await self._call_claude(
                messages=messages,
                system=system,
                max_tokens=800,
                temperature=0.3,
            )

            # Parse JSON response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            qualification = json.loads(response)

            logger.info(
                "qualification_extracted",
                lead_score=qualification.get("qualification", {}).get("lead_score"),
                lead_tier=qualification.get("qualification", {}).get("lead_tier"),
            )

            return qualification

        except json.JSONDecodeError as e:
            logger.error("qualification_json_parse_error", error=str(e))
            return None
        except Exception as e:
            logger.error("qualification_extraction_error", error=str(e))
            return None

    async def analyze_sentiment(self, conversation: str) -> dict[str, Any]:
        """Analyze sentiment and detect escalation needs."""
        prompt_template = self._load_prompt("sentiment-analyzer")

        system = f"""You are a sentiment analysis system for customer service.
Analyze the conversation and determine sentiment and escalation needs.

{prompt_template}

Return ONLY valid JSON."""

        user_message = f"""CONVERSATION:
{conversation}

Analyze and return JSON:
{{
    "sentiment": {{
        "overall": "positive|neutral|negative",
        "score": "number -1 to 1",
        "emotions": ["list of detected emotions"]
    }},
    "customer_state": {{
        "satisfaction": "satisfied|neutral|dissatisfied|frustrated|angry",
        "engagement": "high|medium|low",
        "intent": "inquiry|booking|complaint|information|other"
    }},
    "escalation_assessment": {{
        "requires_escalation": "boolean",
        "escalation_reason": "string or null",
        "urgency": "immediate|same-day|next-day|none",
        "recommended_action": "string"
    }}
}}"""

        messages = [{"role": "user", "content": user_message}]

        try:
            response = await self._call_claude(
                messages=messages,
                system=system,
                max_tokens=500,
                temperature=0.3,
            )

            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            return json.loads(response)

        except Exception as e:
            logger.error("sentiment_analysis_error", error=str(e))
            return {
                "sentiment": {"overall": "neutral", "score": 0},
                "escalation_assessment": {"requires_escalation": False},
            }

    async def generate_summary(self, conversation: str) -> str:
        """Generate a brief summary of a conversation."""
        system = """Generate a brief 2-3 sentence summary of the conversation.
Focus on: what the customer wanted, what was discussed, and any next steps."""

        messages = [{"role": "user", "content": f"Summarize:\n\n{conversation}"}]

        return await self._call_claude(
            messages=messages,
            system=system,
            max_tokens=200,
            temperature=0.5,
        )


# Singleton instance
claude_service = ClaudeService()
