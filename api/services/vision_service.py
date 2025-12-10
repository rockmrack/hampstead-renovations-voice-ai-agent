"""
Vision service for analysing property photos via Claude Vision API.
Provides intelligent responses about project scope and cost estimates.
"""

import base64
import json

import anthropic
import httpx
import structlog
from config import settings
from models.conversation import ImageAnalysis

logger = structlog.get_logger()


class VisionService:
    """Service for analysing property images using Claude Vision."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"

    async def download_whatsapp_media(self, media_url: str, auth_token: str) -> bytes:
        """Download media from WhatsApp servers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url, headers={"Authorization": f"Bearer {auth_token}"}, timeout=30.0
            )
            response.raise_for_status()
            return response.content

    async def analyse_property_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        conversation_context: str | None = None,
    ) -> ImageAnalysis:
        """
        Analyse a property image and extract renovation-relevant information.

        Args:
            image_bytes: Raw image data
            mime_type: MIME type of the image
            conversation_context: Optional context from ongoing conversation

        Returns:
            ImageAnalysis with property details and cost indicators
        """
        base64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

        system_prompt = """You are a property renovation expert for Hampstead Renovations,
        a premium renovation company in North West London. Analyse property photos to assess
        renovation scope and provide helpful guidance.

        Pricing context:
        - Kitchen extensions: £75,000-£220,000
        - Loft conversions: £60,000-£150,000 (dormer), £45,000-£80,000 (velux)
        - Bathroom refurbishments: £15,000-£45,000
        - Full house renovations: £150,000-£500,000+
        - Basement conversions: £200,000-£400,000

        Always be warm, professional, and helpful. Never give exact quotes from photos alone.

        Return your analysis as valid JSON only, no other text."""

        schema = ImageAnalysis.model_json_schema()
        user_prompt = f"""Analyse this property image and provide:
        1. Property type (Victorian terrace, Edwardian semi, modern flat, etc.)
        2. Room type shown
        3. Current condition assessment
        4. Estimated room size if visible
        5. Notable features affecting renovation (period features, structural elements)
        6. Renovation complexity rating
        7. Cost indicators based on what you see
        8. 2-3 follow-up questions I should ask the customer

        {"Previous conversation context: " + conversation_context if conversation_context else ""}

        Return as JSON matching this schema: {json.dumps(schema)}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": base64_image,
                                },
                            },
                            {"type": "text", "text": user_prompt},
                        ],
                    }
                ],
            )

            result = json.loads(response.content[0].text)
            logger.info("image_analysis_complete", property_type=result.get("property_type"))
            return ImageAnalysis(**result)

        except json.JSONDecodeError as e:
            logger.error("image_analysis_json_error", error=str(e))
            return ImageAnalysis(
                renovation_complexity="unknown",
                cost_indicators="Unable to analyse image. Please send a clearer photo.",
                suggested_questions=["Could you send another photo with better lighting?"],
            )
        except Exception as e:
            logger.error("image_analysis_error", error=str(e))
            raise

    def generate_response(self, analysis: ImageAnalysis) -> str:
        """Convert analysis into natural conversational response."""
        response_parts = []

        if analysis.property_type:
            response_parts.append(
                f"Thanks for sharing! I can see you've got a lovely {analysis.property_type}."
            )

        if analysis.room_type:
            response_parts.append(f"This looks like your {analysis.room_type}.")

        if analysis.current_condition:
            condition_responses = {
                "dated": "It's got good bones but could definitely use some updating.",
                "good": "It's in good condition — a great starting point for improvements.",
                "poor": "I can see there's quite a bit of work needed here.",
                "gutted": "Looks like you're ready for a full transformation!",
            }
            if analysis.current_condition.lower() in condition_responses:
                response_parts.append(condition_responses[analysis.current_condition.lower()])

        if analysis.cost_indicators:
            response_parts.append(analysis.cost_indicators)

        if analysis.notable_features:
            features = ", ".join(analysis.notable_features[:2])
            response_parts.append(
                f"I noticed {features} which we'd want to consider in the design."
            )

        if analysis.suggested_questions:
            response_parts.append(f"Quick question — {analysis.suggested_questions[0]}")

        return " ".join(response_parts)


# Singleton instance
vision_service = VisionService()
