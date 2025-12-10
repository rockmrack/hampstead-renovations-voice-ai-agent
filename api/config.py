"""
Configuration management for Hampstead Renovations Voice Agent API.
Uses pydantic-settings for type-safe configuration with environment variables.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Hampstead Voice Agent API"
    app_version: str = "2.0.0"
    debug: bool = False
    debug_mode: bool = False
    testing: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    workers: int = 4
    reload: bool = False

    # API Keys - External Services
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude")
    deepgram_api_key: str = Field(default="", description="Deepgram API key for STT")
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key for TTS")
    vapi_api_key: str = Field(default="", description="VAPI API key for voice calls")
    vapi_assistant_id: str | None = None
    vapi_phone_number_id: str | None = None
    vapi_webhook_secret: str | None = None

    # WhatsApp (360dialog)
    whatsapp_api_key: str = Field(default="", description="360dialog API key")
    whatsapp_api_url: str = "https://waba.360dialog.io/v1"
    whatsapp_phone_number_id: str | None = None

    # Twilio
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None

    # HubSpot CRM
    hubspot_api_key: str = Field(default="", description="HubSpot API key")
    hubspot_portal_id: str | None = None

    # Microsoft Graph (Calendar)
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant_id: str | None = None
    microsoft_redirect_uri: str | None = None
    ross_email: str = "ross@hampsteadrenovations.co.uk"
    ross_mobile_number: str = "+447000000000"

    # AWS
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "eu-west-2"
    aws_s3_bucket: str = "hampstead-renovations-docs"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/hampstead_voice"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600  # 1 hour default
    redis_conversation_ttl: int = 86400  # 24 hours

    # Slack Notifications
    slack_webhook_url: str | None = None
    slack_channel: str = "#voice-agent-alerts"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Sentry
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1

    # Email (SendGrid)
    sendgrid_api_key: str | None = None

    # EPC API for property data
    epc_api_key: str | None = None

    # Feature Flags
    enable_voice_notes: bool = True
    enable_phone_calls: bool = True
    enable_sentiment_analysis: bool = True
    enable_conversation_memory: bool = True
    enable_photo_analysis: bool = True
    enable_auto_followups: bool = True
    enable_appointment_reminders: bool = True
    enable_postcode_enrichment: bool = True

    # Business Configuration
    business_name: str = "Hampstead Renovations"
    business_timezone: str = "Europe/London"
    office_open_hour: int = 8
    office_close_hour: int = 18
    saturday_open_hour: int = 9
    saturday_close_hour: int = 13

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export singleton
settings = get_settings()
