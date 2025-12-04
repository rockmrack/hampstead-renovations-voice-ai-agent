"""
Configuration management for Hampstead Renovations Voice Agent API.
Uses pydantic-settings for type-safe configuration with environment variables.
"""

from functools import lru_cache
from typing import Optional

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
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    workers: int = 4
    reload: bool = False

    # API Keys - External Services
    anthropic_api_key: str = Field(..., min_length=1)
    deepgram_api_key: str = Field(..., min_length=1)
    elevenlabs_api_key: str = Field(..., min_length=1)
    vapi_api_key: str = Field(..., min_length=1)
    vapi_assistant_id: Optional[str] = None
    vapi_webhook_secret: Optional[str] = None

    # WhatsApp (360dialog)
    whatsapp_api_key: str = Field(..., min_length=1)
    whatsapp_api_url: str = "https://waba.360dialog.io/v1"
    whatsapp_phone_number_id: Optional[str] = None

    # Twilio
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None

    # HubSpot CRM
    hubspot_api_key: str = Field(..., min_length=1)
    hubspot_portal_id: Optional[str] = None

    # Microsoft Graph (Calendar)
    microsoft_client_id: Optional[str] = None
    microsoft_client_secret: Optional[str] = None
    microsoft_tenant_id: Optional[str] = None
    microsoft_redirect_uri: Optional[str] = None
    ross_email: str = "ross@hampsteadrenovations.co.uk"
    ross_mobile_number: str = "+447000000000"

    # AWS
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
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
    slack_webhook_url: Optional[str] = None
    slack_channel: str = "#voice-agent-alerts"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Sentry
    sentry_dsn: Optional[str] = None
    sentry_traces_sample_rate: float = 0.1

    # Feature Flags
    enable_voice_notes: bool = True
    enable_phone_calls: bool = True
    enable_sentiment_analysis: bool = True
    enable_conversation_memory: bool = True

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
