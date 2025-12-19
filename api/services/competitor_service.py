"""
Competitor Intelligence Service for Hampstead Renovations Voice AI Agent

Detects competitor mentions and provides strategic responses:
- Competitor name detection
- Differentiation talking points
- Value proposition emphasis
- Competitor weakness awareness (ethical approach)
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

import anthropic
from config import settings

logger = logging.getLogger(__name__)


class CompetitorCategory(Enum):
    """Categories of competitors"""

    DIRECT = "direct"  # Same market, same services
    BUDGET = "budget"  # Lower price point
    PREMIUM = "premium"  # Higher price point
    NATIONAL = "national"  # National chains
    LOCAL = "local"  # Local independents
    ONLINE = "online"  # Online-only services


@dataclass
class Competitor:
    """Competitor information"""

    name: str
    aliases: list[str]
    category: CompetitorCategory
    differentiators: list[str]
    talking_points: list[str]
    known_weaknesses: list[str]


@dataclass
class CompetitorMention:
    """Detected competitor mention"""

    competitor: Competitor
    original_text: str
    context: str
    sentiment: str  # positive, negative, neutral, comparing
    suggested_response: str


class CompetitorIntelligenceService:
    """
    Competitor intelligence and differentiation service

    Provides:
    - Competitor detection in conversations
    - Strategic response generation
    - Differentiation talking points
    - Value proposition reinforcement
    """

    # Known competitors database
    COMPETITORS: dict[str, Competitor] = {
        "abc_builders": Competitor(
            name="ABC Builders",
            aliases=["abc", "abc builder", "abc construction"],
            category=CompetitorCategory.BUDGET,
            differentiators=[
                "Focus on price over quality",
                "Volume-based business model",
                "Standard materials only",
            ],
            talking_points=[
                "Our craftsmen have 15+ years experience in period properties",
                "We use premium materials with 10-year guarantees",
                "Personal project manager throughout your build",
                "Full architectural and planning services included",
            ],
            known_weaknesses=[
                "Communication issues reported",
                "Quality inconsistency",
                "Limited design input",
            ],
        ),
        "simply_extend": Competitor(
            name="Simply Extend",
            aliases=["simply", "simply extensions", "simplyextend"],
            category=CompetitorCategory.NATIONAL,
            differentiators=[
                "Cookie-cutter designs",
                "Remote project management",
                "Subcontracted labour",
            ],
            talking_points=[
                "Our in-house team knows North London's Victorian and Edwardian homes intimately",
                "Bespoke designs tailored to your property's character",
                "Local planning relationships mean smoother approvals",
                "We've completed 500+ projects in NW London alone",
            ],
            known_weaknesses=[
                "Limited customization",
                "Distant project management",
                "Variable local knowledge",
            ],
        ),
        "refresh_renovations": Competitor(
            name="Refresh Renovations",
            aliases=["refresh", "refresh reno"],
            category=CompetitorCategory.DIRECT,
            differentiators=[
                "Franchise model",
                "Variable quality by location",
                "Fixed pricing packages",
            ],
            talking_points=[
                "We're an independent family business with our reputation on every project",
                "Flexible, custom solutions rather than fixed packages",
                "Ross personally oversees every major project",
                "Direct communication with decision-makers",
            ],
            known_weaknesses=["Franchise inconsistency", "Corporate feel", "Limited flexibility"],
        ),
        "build_team": Competitor(
            name="Build Team",
            aliases=["buildteam", "the build team"],
            category=CompetitorCategory.DIRECT,
            differentiators=[
                "Similar market position",
                "Corporate structure",
                "Multiple project managers",
            ],
            talking_points=[
                "Single point of contact throughout your project",
                "Specialist in period property renovations",
                "Award-winning design team",
                "Transparent pricing with no hidden costs",
            ],
            known_weaknesses=[
                "Multiple contact points",
                "Longer lead times",
                "Higher overhead costs",
            ],
        ),
        "checkatrade": Competitor(
            name="Checkatrade Builders",
            aliases=["checkatrade", "check a trade", "trusted traders"],
            category=CompetitorCategory.ONLINE,
            differentiators=["Platform, not builder", "Variable quality", "No accountability"],
            talking_points=[
                "We're vetted and insured specialists, not a marketplace listing",
                "Full design-to-completion service under one roof",
                "Guaranteed fixed pricing before work starts",
                "Portfolio of completed projects you can visit",
            ],
            known_weaknesses=[
                "Inconsistent quality",
                "Limited accountability",
                "Platform fees passed to customers",
            ],
        ),
        "resi": Competitor(
            name="Resi",
            aliases=["resi.co.uk", "resi design", "resiuk"],
            category=CompetitorCategory.ONLINE,
            differentiators=["Design-focused", "No construction arm", "Online-first"],
            talking_points=[
                "We handle everything: design, planning, AND construction",
                "No need to coordinate multiple companies",
                "In-person design consultations",
                "Construction expertise informs our designs from day one",
            ],
            known_weaknesses=["Design only, no build", "Remote service", "Hand-off issues"],
        ),
    }

    # Generic competitor patterns
    COMPETITOR_PATTERNS = [
        r"another (?:builder|company|contractor|firm)",
        r"(?:local|other) builders?",
        r"someone else",
        r"different company",
        r"quote from (?:another|elsewhere)",
        r"comparing (?:quotes|prices|options)",
        r"other options",
        r"shopping around",
        r"got (?:a )?quote",
        r"was quoted",
    ]

    # Hampstead Renovations unique value propositions
    VALUE_PROPOSITIONS = {
        "experience": {
            "point": "15+ years specializing in North West London period properties",
            "proof": "We've completed over 500 projects in the NW London area",
            "benefit": "We understand the unique challenges of Victorian and Edwardian homes",
        },
        "local_expertise": {
            "point": "Deep knowledge of local planning regulations and conservation areas",
            "proof": "95% planning approval rate on first submission",
            "benefit": "Faster approvals and no costly resubmissions",
        },
        "quality": {
            "point": "Premium materials with manufacturer warranties",
            "proof": "All work guaranteed for 10 years",
            "benefit": "Peace of mind and lasting quality",
        },
        "transparency": {
            "point": "Detailed, itemized quotes with no hidden costs",
            "proof": "98% of our projects complete within budget",
            "benefit": "You know exactly what you're paying for",
        },
        "communication": {
            "point": "Dedicated project manager and weekly updates",
            "proof": "Direct line to Ross for any concerns",
            "benefit": "Never feel out of the loop on your own project",
        },
        "design": {
            "point": "Award-winning in-house design team",
            "proof": "Featured in Homes & Gardens and Ideal Home",
            "benefit": "Beautiful, functional spaces that add value",
        },
    }

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"

    async def detect_competitor_mention(
        self, message: str, conversation_context: str | None = None
    ) -> CompetitorMention | None:
        """
        Detect if a competitor is mentioned in the message

        Args:
            message: User's message
            conversation_context: Previous conversation for context

        Returns:
            CompetitorMention if detected, None otherwise
        """
        message_lower = message.lower()

        # Check known competitors
        for _key, competitor in self.COMPETITORS.items():
            # Check name and aliases
            names_to_check = [competitor.name.lower()] + [a.lower() for a in competitor.aliases]

            for name in names_to_check:
                if name in message_lower:
                    sentiment = await self._analyze_sentiment(message, competitor.name)
                    suggested = await self._generate_response(competitor, sentiment, message)

                    return CompetitorMention(
                        competitor=competitor,
                        original_text=message,
                        context=conversation_context or "",
                        sentiment=sentiment,
                        suggested_response=suggested,
                    )

        # Check generic competitor patterns
        for pattern in self.COMPETITOR_PATTERNS:
            if re.search(pattern, message_lower):
                # Generic competitor mention
                generic = Competitor(
                    name="Another Company",
                    aliases=[],
                    category=CompetitorCategory.LOCAL,
                    differentiators=[],
                    talking_points=list(self.VALUE_PROPOSITIONS.values())[0:3],
                    known_weaknesses=[],
                )

                sentiment = await self._analyze_sentiment(message, "competitor")
                suggested = await self._generate_generic_response(message, sentiment)

                return CompetitorMention(
                    competitor=generic,
                    original_text=message,
                    context=conversation_context or "",
                    sentiment=sentiment,
                    suggested_response=suggested,
                )

        return None

    async def _analyze_sentiment(self, message: str, competitor_name: str) -> str:
        """Analyze sentiment towards competitor mention"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Analyze the sentiment in this message about {competitor_name}:
"{message}"

Return only one word: positive, negative, neutral, or comparing""",
                    }
                ],
            )

            sentiment = response.content[0].text.strip().lower()
            if sentiment in ["positive", "negative", "neutral", "comparing"]:
                return sentiment
            return "neutral"

        except Exception:
            return "neutral"

    async def _generate_response(
        self, competitor: Competitor, sentiment: str, original_message: str
    ) -> str:
        """Generate strategic response to competitor mention"""

        # Select appropriate talking points based on sentiment
        if sentiment == "positive":
            # Customer likes competitor - acknowledge and differentiate
            points = competitor.talking_points[:2]
            approach = "acknowledge and differentiate"
        elif sentiment == "negative":
            # Customer has concerns about competitor - empathize and reassure
            points = [vp["point"] for vp in list(self.VALUE_PROPOSITIONS.values())[:2]]
            approach = "empathize and highlight our strengths"
        elif sentiment == "comparing":
            # Customer shopping around - provide clear differentiation
            points = competitor.talking_points
            approach = "clear differentiation with proof points"
        else:
            # Neutral - provide value proposition
            points = [vp["point"] for vp in list(self.VALUE_PROPOSITIONS.values())[:2]]
            approach = "value proposition"

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=f"""You are a helpful assistant for Hampstead Renovations, a premium renovation company in North West London.

Generate a warm, professional response to a customer who has mentioned {competitor.name}.
Approach: {approach}

Key talking points to weave in naturally:
{chr(10).join(f"- {p}" for p in points)}

Guidelines:
- Never disparage competitors directly
- Focus on our unique value
- Be genuine and helpful
- Offer to answer specific questions
- If they have a quote, offer a comparison
- Keep it conversational, not salesy""",
                messages=[
                    {
                        "role": "user",
                        "content": f'Customer said: "{original_message}"\n\nGenerate a helpful response.',
                    }
                ],
            )

            return response.content[0].text.strip()

        except Exception as e:
            logger.error(f"Error generating competitor response: {e}")
            return self._get_fallback_response(sentiment)

    async def _generate_generic_response(self, message: str, sentiment: str) -> str:  # noqa: ARG002
        """Generate response for generic competitor mention"""

        if "quote" in message.lower() or "price" in message.lower():
            return """That's great that you're doing your research - it's such an important decision!

We'd love the opportunity to provide you with a detailed quote. What sets ours apart is:

• Itemized breakdown so you know exactly what you're paying for
• No hidden costs - the price we quote is the price you pay
• We include things others often add as extras: waste removal, all materials, project management

Would you like us to put together a comparison-ready quote? I can arrange for Ross to do a site visit at a time that suits you."""

        elif "compare" in message.lower() or "comparing" in message.lower():
            return """Smart move comparing options - this is a big investment and you want to get it right!

A few things that often matter when comparing:
• What's included in the quote (some companies add extras later)
• Warranty terms - we offer 10 years on all our work
• Who'll actually be managing your project day-to-day
• Their experience with similar properties to yours

Happy to walk you through what's included in our proposals so you can compare like-for-like. Would that be helpful?"""

        else:
            return """It's good to explore your options - this is an important decision!

I'd love to tell you a bit about what makes Hampstead Renovations different. We've been specializing in North West London homes for over 15 years, and our focus on period properties means we understand the unique challenges and opportunities of homes in this area.

Would it help if I arranged for you to speak with Ross directly? He can answer any questions about how we work and what to look for when comparing builders."""

    def _get_fallback_response(self, sentiment: str) -> str:
        """Get fallback response if AI generation fails"""
        if sentiment == "comparing":
            return "It's smart to compare options for such an important project. We'd love the chance to show you what sets Hampstead Renovations apart. Would you like to arrange a no-obligation consultation?"
        return "That's interesting to hear. We pride ourselves on our quality and service. Would you like to know more about what makes Hampstead Renovations different?"

    def get_value_proposition(self, key: str) -> dict | None:
        """Get a specific value proposition"""
        return self.VALUE_PROPOSITIONS.get(key)

    def get_all_value_propositions(self) -> dict:
        """Get all value propositions"""
        return self.VALUE_PROPOSITIONS

    async def generate_comparison_guide(self, services: list[str]) -> str:
        """
        Generate a comparison guide for customers shopping around

        Args:
            services: List of services customer is interested in

        Returns:
            Formatted comparison guide
        """
        services_text = ", ".join(services) if services else "home renovation"

        guide = f"""## What to Look for When Comparing {services_text.title()} Quotes

### 1. Scope of Work
- Is everything itemized?
- What's included vs. what's extra?
- Planning and design included?

### 2. Materials
- Quality of materials specified?
- Brand names or generic?
- Warranties on materials?

### 3. Labour
- In-house team or subcontractors?
- Who's managing the project?
- Experience with similar projects?

### 4. Timeline
- Realistic start date?
- Clear completion date?
- Penalties for delays?

### 5. Guarantees
- Workmanship warranty length?
- What's covered?
- Insurance and liability?

### 6. Communication
- Single point of contact?
- How often will you get updates?
- How to raise concerns?

### Why Customers Choose Hampstead Renovations

✓ **Transparent Pricing**: Itemized quotes, no hidden costs
✓ **10-Year Guarantee**: On all workmanship
✓ **In-House Team**: No subcontractor lottery
✓ **Personal Service**: Direct access to Ross
✓ **Local Expertise**: 500+ NW London projects
✓ **Design Included**: Architectural services in-house

Would you like us to put together a detailed quote so you can compare properly?"""

        return guide


# Module-level instance
competitor_service = CompetitorIntelligenceService()
