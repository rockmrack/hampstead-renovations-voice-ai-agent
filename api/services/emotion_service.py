"""
Voice Emotion Analysis Service for Hampstead Renovations Voice AI Agent

Analyzes voice tone and emotional cues from audio:
- Emotion detection (happy, frustrated, confused, urgent)
- Sentiment analysis from voice characteristics
- Escalation triggers for negative emotions
- Conversation quality monitoring
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import anthropic
from config import settings

logger = logging.getLogger(__name__)


class EmotionType(Enum):
    """Types of emotions detected"""

    HAPPY = "happy"
    SATISFIED = "satisfied"
    NEUTRAL = "neutral"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    ANXIOUS = "anxious"
    URGENT = "urgent"
    INTERESTED = "interested"
    SKEPTICAL = "skeptical"


class EmotionIntensity(Enum):
    """Intensity levels of detected emotions"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EmotionAnalysisResult:
    """Result of emotion analysis"""

    primary_emotion: EmotionType
    secondary_emotion: EmotionType | None
    intensity: EmotionIntensity
    confidence: float
    indicators: list[str]
    suggested_action: str
    escalate: bool = False
    escalation_reason: str | None = None


@dataclass
class VoiceCharacteristics:
    """Voice characteristics extracted from audio"""

    speaking_rate: str  # slow, normal, fast, very_fast
    volume_level: str  # quiet, normal, loud
    pitch_variation: str  # monotone, normal, varied, highly_varied
    pause_frequency: str  # none, occasional, frequent
    speech_clarity: str  # unclear, normal, clear


@dataclass
class ConversationEmotionTrack:
    """Track emotions throughout a conversation"""

    conversation_id: str
    emotion_timeline: list[tuple[datetime, EmotionAnalysisResult]] = field(default_factory=list)
    overall_sentiment: str = "neutral"
    escalation_events: list[dict] = field(default_factory=list)


class EmotionAnalysisService:
    """
    Voice emotion analysis service

    Provides:
    - Text-based emotion detection (from transcripts)
    - Voice characteristic analysis
    - Escalation triggers
    - Conversation quality monitoring
    """

    # Emotion keywords and patterns
    EMOTION_INDICATORS = {
        EmotionType.HAPPY: [
            "wonderful",
            "fantastic",
            "great",
            "love",
            "perfect",
            "excellent",
            "amazing",
            "brilliant",
            "thank you so much",
            "really pleased",
        ],
        EmotionType.SATISFIED: [
            "good",
            "nice",
            "happy with",
            "that works",
            "sounds good",
            "fine",
            "okay great",
            "that's helpful",
            "appreciate",
        ],
        EmotionType.CONFUSED: [
            "don't understand",
            "what do you mean",
            "confused",
            "not sure",
            "can you explain",
            "lost me",
            "unclear",
            "what?",
            "sorry?",
            "could you repeat",
            "i'm not following",
        ],
        EmotionType.FRUSTRATED: [
            "frustrat",
            "annoying",
            "already told",
            "again",
            "how many times",
            "not working",
            "still waiting",
            "this is ridiculous",
            "unacceptable",
            "waste of time",
            "getting nowhere",
        ],
        EmotionType.ANGRY: [
            "furious",
            "outrageous",
            "disgusted",
            "terrible",
            "worst",
            "never again",
            "complaint",
            "legal",
            "trading standards",
            "ombudsman",
        ],
        EmotionType.ANXIOUS: [
            "worried",
            "nervous",
            "concerned",
            "scary",
            "anxious",
            "uncertain",
            "not sure if",
            "what if",
            "risky",
            "afraid",
        ],
        EmotionType.URGENT: [
            "urgent",
            "emergency",
            "asap",
            "right now",
            "immediately",
            "today",
            "can't wait",
            "deadline",
            "time sensitive",
            "critical",
        ],
        EmotionType.INTERESTED: [
            "tell me more",
            "interested",
            "curious",
            "how does that work",
            "what about",
            "can you",
            "i'd like to know",
            "sounds interesting",
        ],
        EmotionType.SKEPTICAL: [
            "really?",
            "are you sure",
            "seems expensive",
            "don't believe",
            "doubt",
            "sounds too good",
            "what's the catch",
            "hidden",
            "but",
        ],
    }

    # Escalation thresholds
    ESCALATION_TRIGGERS = {
        EmotionType.ANGRY: EmotionIntensity.MEDIUM,
        EmotionType.FRUSTRATED: EmotionIntensity.HIGH,
        EmotionType.ANXIOUS: EmotionIntensity.HIGH,
    }

    # Response adaptations based on emotion
    RESPONSE_ADAPTATIONS = {
        EmotionType.HAPPY: {
            "tone": "enthusiastic and warm",
            "approach": "Match their energy, reinforce positive feelings",
            "action": "Great opportunity to ask for referrals or reviews",
        },
        EmotionType.SATISFIED: {
            "tone": "warm and professional",
            "approach": "Maintain momentum, confirm next steps clearly",
            "action": "Good time to discuss additional services",
        },
        EmotionType.CONFUSED: {
            "tone": "patient and clear",
            "approach": "Slow down, use simpler language, offer to explain differently",
            "action": "Ask what specifically needs clarification",
        },
        EmotionType.FRUSTRATED: {
            "tone": "empathetic and solution-focused",
            "approach": "Acknowledge frustration, take ownership, offer concrete solutions",
            "action": "Consider offering to escalate to Ross directly",
        },
        EmotionType.ANGRY: {
            "tone": "calm and understanding",
            "approach": "Let them vent, apologize sincerely, focus on resolution",
            "action": "Immediate escalation to human agent",
        },
        EmotionType.ANXIOUS: {
            "tone": "reassuring and informative",
            "approach": "Address concerns directly, provide reassurance with facts",
            "action": "Offer detailed information and guarantees",
        },
        EmotionType.URGENT: {
            "tone": "efficient and action-oriented",
            "approach": "Acknowledge urgency, prioritize their request",
            "action": "Fast-track to appropriate team member",
        },
        EmotionType.INTERESTED: {
            "tone": "engaging and informative",
            "approach": "Provide detailed information, share relevant examples",
            "action": "Opportunity to schedule consultation",
        },
        EmotionType.SKEPTICAL: {
            "tone": "transparent and factual",
            "approach": "Provide evidence, testimonials, address concerns directly",
            "action": "Offer references or portfolio examples",
        },
    }

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5-20250514"
        self._conversation_tracks: dict[str, ConversationEmotionTrack] = {}

    async def analyze_text_emotion(
        self, text: str, conversation_context: str | None = None
    ) -> EmotionAnalysisResult:
        """
        Analyze emotion from text (transcript)

        Args:
            text: Text to analyze (usually voice transcript)
            conversation_context: Previous messages for context

        Returns:
            EmotionAnalysisResult with detected emotion and recommendations
        """
        text_lower = text.lower()

        # First pass: keyword matching
        detected_emotions: dict[EmotionType, int] = {}
        indicators_found: list[str] = []

        for emotion, keywords in self.EMOTION_INDICATORS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    detected_emotions[emotion] = detected_emotions.get(emotion, 0) + 1
                    indicators_found.append(f"'{keyword}' suggests {emotion.value}")

        # If keywords found, use that as primary detection
        if detected_emotions:
            primary = max(detected_emotions, key=detected_emotions.get)
            intensity = self._calculate_intensity(detected_emotions[primary], text_lower)

            # Get secondary emotion if exists
            secondary = None
            if len(detected_emotions) > 1:
                emotions_sorted = sorted(
                    detected_emotions.items(), key=lambda x: x[1], reverse=True
                )
                secondary = emotions_sorted[1][0]

        else:
            # Use AI for nuanced analysis
            analysis = await self._ai_emotion_analysis(text, conversation_context)
            primary = analysis.get("primary", EmotionType.NEUTRAL)
            secondary = analysis.get("secondary")
            intensity = analysis.get("intensity", EmotionIntensity.LOW)
            indicators_found = analysis.get("indicators", [])

        # Determine if escalation needed
        escalate = False
        escalation_reason = None

        if primary in self.ESCALATION_TRIGGERS:
            threshold = self.ESCALATION_TRIGGERS[primary]
            if self._intensity_exceeds_threshold(intensity, threshold):
                escalate = True
                escalation_reason = (
                    f"{primary.value} emotion detected at {intensity.value} intensity"
                )

        # Get suggested action
        adaptation = self.RESPONSE_ADAPTATIONS.get(
            primary, self.RESPONSE_ADAPTATIONS[EmotionType.NEUTRAL]
        )
        suggested_action = adaptation["action"]

        return EmotionAnalysisResult(
            primary_emotion=primary,
            secondary_emotion=secondary,
            intensity=intensity,
            confidence=0.8 if detected_emotions else 0.6,
            indicators=indicators_found[:5],  # Limit to top 5
            suggested_action=suggested_action,
            escalate=escalate,
            escalation_reason=escalation_reason,
        )

    async def _ai_emotion_analysis(self, text: str, context: str | None) -> dict:
        """Use AI for nuanced emotion analysis"""
        try:
            context_note = f"\nConversation context: {context}" if context else ""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Analyze the emotion in this customer message:
"{text}"
{context_note}

Return JSON only:
{{
    "primary_emotion": "happy|satisfied|neutral|confused|frustrated|angry|anxious|urgent|interested|skeptical",
    "secondary_emotion": "emotion or null",
    "intensity": "low|medium|high|critical",
    "indicators": ["list of emotional cues detected"]
}}""",
                    }
                ],
            )

            result = json.loads(response.content[0].text)

            # Convert strings to enums
            primary_str = result.get("primary_emotion", "neutral")
            primary = (
                EmotionType(primary_str)
                if primary_str in [e.value for e in EmotionType]
                else EmotionType.NEUTRAL
            )

            secondary = None
            if result.get("secondary_emotion"):
                sec_str = result["secondary_emotion"]
                secondary = (
                    EmotionType(sec_str) if sec_str in [e.value for e in EmotionType] else None
                )

            intensity_str = result.get("intensity", "low")
            intensity = (
                EmotionIntensity(intensity_str)
                if intensity_str in [i.value for i in EmotionIntensity]
                else EmotionIntensity.LOW
            )

            return {
                "primary": primary,
                "secondary": secondary,
                "intensity": intensity,
                "indicators": result.get("indicators", []),
            }

        except Exception as e:
            logger.error(f"AI emotion analysis failed: {e}")
            return {
                "primary": EmotionType.NEUTRAL,
                "secondary": None,
                "intensity": EmotionIntensity.LOW,
                "indicators": [],
            }

    def _calculate_intensity(self, keyword_count: int, text: str) -> EmotionIntensity:
        """Calculate emotion intensity based on various factors"""
        # Exclamation marks increase intensity
        exclamation_count = text.count("!")

        # All caps words increase intensity
        words = text.split()
        caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)

        # Calculate score
        score = keyword_count + (exclamation_count * 0.5) + (caps_words * 0.5)

        if score >= 5:
            return EmotionIntensity.CRITICAL
        elif score >= 3:
            return EmotionIntensity.HIGH
        elif score >= 2:
            return EmotionIntensity.MEDIUM
        else:
            return EmotionIntensity.LOW

    def _intensity_exceeds_threshold(
        self, intensity: EmotionIntensity, threshold: EmotionIntensity
    ) -> bool:
        """Check if intensity exceeds threshold"""
        levels = [
            EmotionIntensity.LOW,
            EmotionIntensity.MEDIUM,
            EmotionIntensity.HIGH,
            EmotionIntensity.CRITICAL,
        ]
        return levels.index(intensity) >= levels.index(threshold)

    async def analyze_voice_characteristics(
        self, transcript: str, audio_duration_seconds: float, word_count: int | None = None
    ) -> VoiceCharacteristics:
        """
        Infer voice characteristics from transcript metadata

        Args:
            transcript: Voice transcript
            audio_duration_seconds: Duration of audio
            word_count: Number of words (if available)

        Returns:
            VoiceCharacteristics inference
        """
        if word_count is None:
            word_count = len(transcript.split())

        # Calculate speaking rate (words per minute)
        wpm = (word_count / audio_duration_seconds) * 60 if audio_duration_seconds > 0 else 0

        if wpm < 100:
            speaking_rate = "slow"
        elif wpm < 150:
            speaking_rate = "normal"
        elif wpm < 180:
            speaking_rate = "fast"
        else:
            speaking_rate = "very_fast"

        # Analyze punctuation for pause frequency
        sentences = transcript.count(".") + transcript.count("!") + transcript.count("?")
        pause_indicator = sentences / word_count if word_count > 0 else 0

        if pause_indicator < 0.05:
            pause_frequency = "none"
        elif pause_indicator < 0.1:
            pause_frequency = "occasional"
        else:
            pause_frequency = "frequent"

        # Pitch variation from punctuation variety
        has_questions = "?" in transcript
        has_exclamations = "!" in transcript
        has_ellipsis = "..." in transcript

        variation_count = sum([has_questions, has_exclamations, has_ellipsis])

        if variation_count == 0:
            pitch_variation = "monotone"
        elif variation_count == 1:
            pitch_variation = "normal"
        elif variation_count == 2:
            pitch_variation = "varied"
        else:
            pitch_variation = "highly_varied"

        return VoiceCharacteristics(
            speaking_rate=speaking_rate,
            volume_level="normal",  # Can't determine from transcript
            pitch_variation=pitch_variation,
            pause_frequency=pause_frequency,
            speech_clarity="normal",  # Can't determine from transcript
        )

    async def track_conversation_emotion(
        self, conversation_id: str, message: str, context: str | None = None
    ) -> EmotionAnalysisResult:
        """
        Track emotion for a conversation over time

        Args:
            conversation_id: Unique conversation identifier
            message: Current message to analyze
            context: Previous context

        Returns:
            EmotionAnalysisResult for current message
        """
        # Get or create track
        if conversation_id not in self._conversation_tracks:
            self._conversation_tracks[conversation_id] = ConversationEmotionTrack(
                conversation_id=conversation_id
            )

        track = self._conversation_tracks[conversation_id]

        # Analyze current message
        result = await self.analyze_text_emotion(message, context)

        # Add to timeline
        track.emotion_timeline.append((datetime.utcnow(), result))

        # Check for escalation
        if result.escalate:
            track.escalation_events.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "emotion": result.primary_emotion.value,
                    "intensity": result.intensity.value,
                    "reason": result.escalation_reason,
                }
            )

        # Update overall sentiment
        track.overall_sentiment = self._calculate_overall_sentiment(track)

        return result

    def _calculate_overall_sentiment(self, track: ConversationEmotionTrack) -> str:
        """Calculate overall conversation sentiment"""
        if not track.emotion_timeline:
            return "neutral"

        # Weight recent emotions more heavily
        positive_emotions = {EmotionType.HAPPY, EmotionType.SATISFIED, EmotionType.INTERESTED}
        negative_emotions = {EmotionType.FRUSTRATED, EmotionType.ANGRY, EmotionType.ANXIOUS}

        recent_emotions = track.emotion_timeline[-5:]  # Last 5 messages

        positive_count = sum(
            1 for _, e in recent_emotions if e.primary_emotion in positive_emotions
        )
        negative_count = sum(
            1 for _, e in recent_emotions if e.primary_emotion in negative_emotions
        )

        if positive_count > negative_count * 2:
            return "positive"
        elif negative_count > positive_count * 2:
            return "negative"
        elif positive_count > negative_count:
            return "slightly_positive"
        elif negative_count > positive_count:
            return "slightly_negative"
        else:
            return "neutral"

    def get_response_adaptation(self, emotion: EmotionType) -> dict:
        """Get response adaptation guidelines for an emotion"""
        return self.RESPONSE_ADAPTATIONS.get(
            emotion, self.RESPONSE_ADAPTATIONS[EmotionType.NEUTRAL]
        )

    async def get_conversation_summary(self, conversation_id: str) -> dict | None:
        """Get emotion summary for a conversation"""
        track = self._conversation_tracks.get(conversation_id)
        if not track:
            return None

        # Calculate emotion distribution
        emotion_counts: dict[str, int] = {}
        for _, result in track.emotion_timeline:
            emotion = result.primary_emotion.value
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

        return {
            "conversation_id": conversation_id,
            "total_messages_analyzed": len(track.emotion_timeline),
            "overall_sentiment": track.overall_sentiment,
            "emotion_distribution": emotion_counts,
            "escalation_events": len(track.escalation_events),
            "escalation_details": track.escalation_events,
        }

    async def should_escalate_to_human(
        self, conversation_id: str, current_emotion: EmotionAnalysisResult
    ) -> tuple[bool, str]:
        """
        Determine if conversation should be escalated to human

        Args:
            conversation_id: Conversation identifier
            current_emotion: Current emotion analysis

        Returns:
            Tuple of (should_escalate, reason)
        """
        track = self._conversation_tracks.get(conversation_id)

        # Immediate escalation for anger or high frustration
        if current_emotion.escalate:
            return True, current_emotion.escalation_reason or "Negative emotion detected"

        if not track:
            return False, ""

        # Check for persistent negative emotions
        recent = (
            track.emotion_timeline[-3:]
            if len(track.emotion_timeline) >= 3
            else track.emotion_timeline
        )
        negative_emotions = {EmotionType.FRUSTRATED, EmotionType.ANGRY, EmotionType.ANXIOUS}

        negative_count = sum(1 for _, e in recent if e.primary_emotion in negative_emotions)

        if negative_count >= 2:
            return True, "Persistent negative emotions detected across multiple messages"

        # Check for escalation event count
        if len(track.escalation_events) >= 2:
            return True, "Multiple escalation triggers in conversation"

        return False, ""


# Module-level instance
emotion_service = EmotionAnalysisService()
