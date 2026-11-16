from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "VendorIQ API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "dev-insecure-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/vendoriq"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Stripe Sandbox Configuration
    STRIPE_SECRET_KEY: str = "sk_test_replace_me"
    STRIPE_PUBLISHABLE_KEY: str = "pk_test_replace_me"
    STRIPE_WEBHOOK_SECRET: str = "whsec_replace_me"
    STRIPE_CURRENCY: str = "usd"
    FRONTEND_URL: str = "http://localhost:3000"
    STRIPE_SUCCESS_URL: str = "http://localhost:3000/checkout/success"
    STRIPE_CANCEL_URL: str = "http://localhost:3000/checkout/cancel"
    CHECKOUT_RESERVATION_MINUTES: int = 30

    # AI Agent / Gemini & WhatsApp Bot
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    AI_SESSION_TTL_MINUTES: int = 60
    AI_SESSION_MAX_TURNS: int = 20
    WHATSAPP_SESSION_NAME: str = "vendoriq_whatsapp.db"

    @property
    def PROJECT_NAME(self) -> str:
        return self.APP_NAME

    @property
    def API_PREFIX(self) -> str:
        return self.API_V1_PREFIX

    @field_validator("STRIPE_SECRET_KEY")
    @classmethod
    def validate_stripe_test_mode(cls, v: str, info) -> str:
        env = info.data.get("APP_ENV", "development")
        if env in ("development", "test", "testing") and v.startswith("sk_live_"):
            raise ValueError(
                "Live-mode Stripe secret keys are strictly prohibited in development and test environments."
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
