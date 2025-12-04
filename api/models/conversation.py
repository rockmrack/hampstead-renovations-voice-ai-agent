"""
Conversation and message models for the Voice Agent.
Pydantic models for request/response validation.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class MessageType(str, Enum):
    """Types of WhatsApp messages."""
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"


class MessageDirection(str, Enum):
    """Message direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class LeadTier(str, Enum):
    """Lead qualification tiers."""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    UNQUALIFIED = "unqualified"


class UrgencyLevel(str, Enum):
    """Urgency levels for projects."""
    IMMEDIATE = "immediate"
    THIS_WEEK = "this-week"
    THIS_MONTH = "this-month"
    FLEXIBLE = "flexible"
    JUST_RESEARCHING = "just-researching"


class SentimentType(str, Enum):
    """Sentiment analysis results."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"


# ============================================
# WhatsApp Models
# ============================================

class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message model."""
    
    message_id: str = Field(..., description="Unique message ID from WhatsApp")
    from_number: str = Field(..., alias="from", description="Sender phone number")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: MessageType = MessageType.TEXT
    text: Optional[str] = None
    audio_url: Optional[str] = None
    audio_id: Optional[str] = None
    caption: Optional[str] = None
    
    class Config:
        populate_by_name = True

    @field_validator("from_number", mode="before")
    @classmethod
    def clean_phone_number(cls, v: str) -> str:
        """Ensure phone number is in E.164 format."""
        if v and not v.startswith("+"):
            v = f"+{v}"
        return v


class WhatsAppWebhookPayload(BaseModel):
    """
    360dialog WhatsApp webhook payload structure.
    Simplified to extract the essential fields.
    """
    
    object: str = "whatsapp_business_account"
    entry: list[dict] = Field(default_factory=list)

    def get_messages(self) -> list[WhatsAppMessage]:
        """Extract messages from webhook payload."""
        messages = []
        
        for entry in self.entry:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                msgs = value.get("messages", [])
                
                for msg in msgs:
                    try:
                        msg_type = msg.get("type", "text")
                        
                        message = WhatsAppMessage(
                            message_id=msg.get("id", ""),
                            from_number=msg.get("from", ""),
                            timestamp=datetime.fromtimestamp(int(msg.get("timestamp", 0))),
                            type=MessageType(msg_type) if msg_type in MessageType.__members__.values() else MessageType.TEXT,
                        )
                        
                        # Extract content based on type
                        if msg_type == "text":
                            message.text = msg.get("text", {}).get("body", "")
                        elif msg_type == "audio":
                            audio = msg.get("audio", {})
                            message.audio_id = audio.get("id")
                            message.audio_url = audio.get("url")
                        
                        messages.append(message)
                        
                    except Exception:
                        continue
        
        return messages


class VoiceNote(BaseModel):
    """Voice note processing model."""
    
    phone: str
    audio_url: str
    duration_seconds: Optional[int] = None
    transcript: Optional[str] = None
    transcription_confidence: Optional[float] = None
    processed_at: Optional[datetime] = None


# ============================================
# Conversation Context Models
# ============================================

class ConversationContext(BaseModel):
    """
    Conversation context stored in Redis.
    Maintains state across multiple messages.
    """
    
    phone: str
    channel: str = "whatsapp"
    
    # Customer info extracted from conversation
    name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    postcode: Optional[str] = None
    
    # Project info
    project_type: Optional[str] = None
    project_description: Optional[str] = None
    timeline: Optional[str] = None
    budget_range: Optional[str] = None
    property_type: Optional[str] = None
    
    # Conversation state
    messages_count: int = 0
    last_message_at: Optional[datetime] = None
    sentiment: Optional[SentimentType] = None
    
    # Lead status
    lead_score: Optional[int] = None
    lead_tier: Optional[LeadTier] = None
    hubspot_contact_id: Optional[str] = None
    
    # Booking info
    survey_booked: bool = False
    survey_date: Optional[str] = None
    survey_time: Optional[str] = None
    calendar_event_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for Redis storage."""
        return {k: str(v) if v is not None else "" for k, v in self.model_dump().items()}

    @classmethod
    def from_redis(cls, data: dict) -> "ConversationContext":
        """Create from Redis hash."""
        # Convert empty strings back to None
        cleaned = {k: v if v else None for k, v in data.items()}
        
        # Handle numeric fields
        if cleaned.get("messages_count"):
            cleaned["messages_count"] = int(cleaned["messages_count"])
        if cleaned.get("lead_score"):
            cleaned["lead_score"] = int(cleaned["lead_score"])
        if cleaned.get("survey_booked"):
            cleaned["survey_booked"] = cleaned["survey_booked"].lower() == "true"
            
        return cls(**cleaned)


# ============================================
# Lead Qualification Models
# ============================================

class ProjectDetails(BaseModel):
    """Project details extracted from conversation."""
    
    type: Optional[str] = Field(None, description="E.g., kitchen, bathroom, extension")
    description: Optional[str] = None
    timeline: Optional[str] = None
    budget_range: Optional[str] = None
    property_type: Optional[str] = None
    special_requirements: Optional[list[str]] = None


class ContactInfo(BaseModel):
    """Contact information extracted from conversation."""
    
    name: Optional[str] = None
    email: Optional[str] = None
    phone: str
    address: Optional[str] = None
    postcode: Optional[str] = None
    preferred_contact_time: Optional[str] = None


class QualificationScore(BaseModel):
    """Lead qualification scoring."""
    
    lead_score: int = Field(..., ge=0, le=100)
    lead_tier: LeadTier
    urgency: UrgencyLevel = UrgencyLevel.FLEXIBLE
    buying_signals: Optional[list[str]] = None
    objections: Optional[list[str]] = None
    next_action: Optional[str] = None


class LeadQualification(BaseModel):
    """
    Complete lead qualification output from AI analysis.
    Matches the output format of the qualification-extractor prompt.
    """
    
    qualification: QualificationScore
    project: ProjectDetails
    contact: ContactInfo
    conversation_summary: Optional[str] = None
    recommended_follow_up: Optional[str] = None
    notes: Optional[str] = None


# ============================================
# Survey Booking Models
# ============================================

class TimeSlot(BaseModel):
    """Available time slot for booking."""
    
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    time: str = Field(..., description="Time in HH:MM format")
    datetime: str = Field(..., description="ISO datetime string")
    duration: int = Field(60, description="Duration in minutes")
    available: bool = True


class SurveyBooking(BaseModel):
    """Survey booking request/response."""
    
    # Customer details
    name: str
    phone: str
    email: Optional[str] = None
    
    # Property details
    address: str
    postcode: Optional[str] = None
    property_type: Optional[str] = None
    
    # Project details
    project_type: Optional[str] = None
    project_description: Optional[str] = None
    
    # Booking details
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    time: str = Field(..., description="Time in HH:MM format")
    duration_minutes: int = 60
    
    # Status
    status: str = "pending"  # pending, confirmed, cancelled, completed
    calendar_event_id: Optional[str] = None
    confirmation_sent: bool = False
    reminder_sent: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None


# ============================================
# API Response Models
# ============================================

class ConversationResponse(BaseModel):
    """Response to a conversation message."""
    
    message: str
    audio_url: Optional[str] = None
    follow_up_action: Optional[str] = None
    qualification_updated: bool = False


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = "ok"
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Standard error response."""
    
    error: str
    message: str
    request_id: Optional[str] = None
    details: Optional[dict] = None
