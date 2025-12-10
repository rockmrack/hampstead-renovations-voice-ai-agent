"""
Claude AI service for conversation handling.
Handles all Anthropic Claude API interactions with retry logic and circuit breaker.
"""

import json
import re
from pathlib import Path
from typing import Any

import anthropic
import structlog
from config import settings
from models.conversation import HandoffDecision, HandoffReason
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


# Trigger phrases for explicit human handoff request
EXPLICIT_HANDOFF_TRIGGERS = [
    "speak to ross",
    "talk to ross",
    "speak to someone",
    "talk to a human",
    "real person",
    "call me",
    "ring me",
    "speak to the owner",
    "manager",
    "boss",
]

# Complaint/anger signals
COMPLAINT_SIGNALS = [
    "disgusted",
    "furious",
    "terrible",
    "worst",
    "sue",
    "solicitor",
    "lawyer",
    "trading standards",
]

# Frustration signals
FRUSTRATION_SIGNALS = [
    "frustrated",
    "annoying",
    "ridiculous",
    "waste of time",
    "not helpful",
    "useless",
    "awful",
    "pathetic",
]


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

    async def check_handoff_required(
        self,
        message: str,
        conversation_history: list[dict],
        lead_data: dict | None = None,  # noqa: ARG002 - Reserved for future lead-based rules
    ) -> HandoffDecision:
        """
        Evaluate if conversation should be handed to Ross.

        Args:
            message: Latest customer message
            conversation_history: Previous messages in conversation
            lead_data: Optional lead data for context

        Returns:
            HandoffDecision with recommendation and context
        """
        message_lower = message.lower()

        # Rule-based checks first (fast)

        # Explicit request for human
        if any(trigger in message_lower for trigger in EXPLICIT_HANDOFF_TRIGGERS):
            return HandoffDecision(
                should_handoff=True,
                reason=HandoffReason.EXPLICIT_REQUEST,
                urgency="immediate",
                context_for_ross="Customer explicitly requested to speak with you.",
            )

        # Complaint detection
        if any(signal in message_lower for signal in COMPLAINT_SIGNALS):
            return HandoffDecision(
                should_handoff=True,
                reason=HandoffReason.COMPLAINT,
                urgency="immediate",
                context_for_ross="Customer appears to be making a complaint or is very unhappy.",
            )

        # Frustration detection
        if any(signal in message_lower for signal in FRUSTRATION_SIGNALS):
            return HandoffDecision(
                should_handoff=True,
                reason=HandoffReason.NEGATIVE_SENTIMENT,
                urgency="same_day",
                context_for_ross="Customer is expressing frustration.",
            )

        # High value detection (budget mentions)
        budget_match = re.search(r"£\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:k|K|000)?", message)
        if budget_match:
            amount_str = budget_match.group(1).replace(",", "")
            amount = float(amount_str)
            if "k" in message_lower or "K" in message:
                amount *= 1000
            if amount >= 200000:
                return HandoffDecision(
                    should_handoff=True,
                    reason=HandoffReason.HIGH_VALUE,
                    urgency="same_day",
                    context_for_ross=f"High-value project mentioned: £{amount:,.0f}",
                )

        # LLM-based evaluation for complex cases
        full_context = "\n".join(
            [f"{m['role']}: {m['content']}" for m in conversation_history[-10:]]
        )

        eval_prompt = f"""Evaluate if this conversation needs human handoff.

CONVERSATION:
{full_context}

LATEST MESSAGE:
{message}

Should this be handed to Ross (the business owner) if ANY of these apply:
1. Customer sentiment is negative/frustrated (not just price-concerned, actually upset)
2. Complex planning permission questions the AI shouldn't answer definitively
3. Customer is comparing with specific competitors and needs persuasion
4. Technical questions about structural work that need expert opinion
5. Customer is ready to proceed and wants to discuss contract/deposit

Return JSON:
{{
    "should_handoff": true/false,
    "reason": "one of: high_value_project, negative_sentiment, complex_planning_question, competitor_comparison, explicit_request, complaint, null",
    "urgency": "immediate/same_day/next_available",
    "context_for_ross": "1-2 sentence summary for Ross"
}}

If no handoff needed, return should_handoff: false with reason: null."""

        try:
            response = await self._call_claude(
                messages=[{"role": "user", "content": eval_prompt}],
                system="You are a handoff evaluation system. Return only valid JSON.",
                max_tokens=200,
                temperature=0.3,
            )

            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            result = json.loads(response)

            # Map string reason to enum
            reason_str = result.get("reason")
            reason = None
            if reason_str:
                reason_map = {
                    "high_value_project": HandoffReason.HIGH_VALUE,
                    "negative_sentiment": HandoffReason.NEGATIVE_SENTIMENT,
                    "complex_planning_question": HandoffReason.COMPLEX_PLANNING,
                    "competitor_comparison": HandoffReason.COMPETITOR_MENTION,
                    "explicit_request": HandoffReason.EXPLICIT_REQUEST,
                    "complaint": HandoffReason.COMPLAINT,
                }
                reason = reason_map.get(reason_str)

            return HandoffDecision(
                should_handoff=result.get("should_handoff", False),
                reason=reason,
                urgency=result.get("urgency", "next_available"),
                context_for_ross=result.get("context_for_ross", ""),
            )

        except Exception as e:
            logger.error("handoff_evaluation_error", error=str(e))
            return HandoffDecision(
                should_handoff=False,
                reason=None,
                urgency="next_available",
                context_for_ross="",
            )

    async def execute_handoff(
        self,
        decision: HandoffDecision,
        lead: dict,
        conversation_id: str,
        notification_service=None,
    ) -> str:
        """
        Execute the handoff - notify Ross and generate customer response.

        Args:
            decision: Handoff decision with reason and urgency
            lead: Lead data dictionary
            conversation_id: Conversation identifier
            notification_service: Notification service for alerts

        Returns:
            Response message to send to customer
        """
        # Notify Ross via Slack if notification service available
        if notification_service:
            slack_message = f"""*HANDOFF REQUIRED* - {decision.urgency.upper()}

*Customer:* {lead.get("name", "Unknown")} ({lead.get("phone")})
*Reason:* {decision.reason.value if decision.reason else "Unknown"}
*Context:* {decision.context_for_ross}

Conversation ID: {conversation_id}"""

            await notification_service.notify_slack(slack_message)

            # Send SMS to Ross for immediate urgency
            if decision.urgency == "immediate":
                await notification_service.send_sms_alert(
                    f"URGENT: Customer {lead.get('name', '')} needs callback. {decision.context_for_ross}"
                )

        logger.info(
            "handoff_executed",
            conversation_id=conversation_id,
            reason=decision.reason.value if decision.reason else None,
            urgency=decision.urgency,
        )

        # Generate customer response
        return self._generate_handoff_response(decision)

    def _generate_handoff_response(self, decision: HandoffDecision) -> str:
        """Generate appropriate message to tell customer Ross will call."""
        responses = {
            HandoffReason.EXPLICIT_REQUEST: "Of course! I'll get Ross to give you a call personally. He's usually able to call back within a couple of hours during office hours. Is this the best number to reach you on?",
            HandoffReason.HIGH_VALUE: "This sounds like a fantastic project! Given the scope, I think it's best Ross speaks with you directly. He'll call you within the next few hours to discuss in detail. Is there a particular time that works best?",
            HandoffReason.NEGATIVE_SENTIMENT: "I can hear you're frustrated, and I'm really sorry about that. Let me get Ross to call you personally to sort this out properly. He takes customer concerns very seriously. He'll be in touch within the hour.",
            HandoffReason.COMPLEX_PLANNING: "That's a great question about planning permission - it's quite nuanced for your specific situation. I want to make sure you get accurate advice, so I'll have Ross call you to discuss the specifics. He's dealt with hundreds of planning applications in the area.",
            HandoffReason.COMPLAINT: "I'm really sorry to hear this. I'm escalating this to Ross immediately and he'll call you as soon as possible to address your concerns personally.",
            HandoffReason.COMPETITOR_MENTION: "I appreciate you're doing your research - that's smart. Let me have Ross call you directly to discuss how we compare and what we can offer for your specific project.",
        }

        if decision.reason and decision.reason in responses:
            return responses[decision.reason]

        return "Let me get Ross to give you a call to discuss further. He'll be in touch shortly."


# Singleton instance
claude_service = ClaudeService()
