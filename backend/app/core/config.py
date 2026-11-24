import logging
import secrets
from typing import Optional

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)


def is_placeholder_secret(value: str | None) -> bool:
    normalized = (value or "").strip().casefold()
    if not normalized:
        return True
    return normalized.startswith((
        "replace", "change-me", "changeme", "example", "placeholder", "your-", "your_",
    )) or normalized in {"default", "secret", "password", "admin", "test"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/intellistock"
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    initial_admin_password: Optional[SecretStr] = None
    allow_public_registration: bool = False
    allow_sqlite_fallback: Optional[bool] = None
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    observability_enabled: bool = True
    observability_ingest_secret: str = ""
    slow_query_ms: int = 200
    network_allowlist: str = "8000,5432,5173,8080"
    sensitive_paths: str = "/.env,/etc/passwd,/etc/shadow,/root/.ssh,/.ssh,backend/intellistock.db"
    ebpf_collector_enabled: bool = False
    chatbot_confidence_threshold: float = 0.45
    chatbot_llm_enabled: bool = False
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    @model_validator(mode="after")
    def validate_runtime_environment(self) -> "Settings":
        self.app_env = self.app_env.strip().casefold()
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")

        if self.allow_sqlite_fallback is None:
            self.allow_sqlite_fallback = self.app_env != "production"

        ingest_secret = self.observability_ingest_secret.strip()
        admin_password = (
            self.initial_admin_password.get_secret_value()
            if self.initial_admin_password is not None
            else ""
        )
        if self.app_env == "production":
            problems: list[str] = []
            if (
                "secret_key" not in self.model_fields_set
                or len(self.secret_key.strip()) < 32
                or is_placeholder_secret(self.secret_key)
            ):
                problems.append("SECRET_KEY must be explicitly configured as a non-placeholder value of at least 32 characters")
            if len(admin_password) < 12 or is_placeholder_secret(admin_password):
                problems.append("INITIAL_ADMIN_PASSWORD must be a non-placeholder value of at least 12 characters")
            if len(ingest_secret) < 32 or is_placeholder_secret(ingest_secret):
                problems.append("OBSERVABILITY_INGEST_SECRET must be a non-placeholder value of at least 32 characters")
            if problems:
                raise ValueError("APP_ENV=production requires valid secrets: " + "; ".join(problems))
        else:
            insecure: list[str] = []
            if "secret_key" in self.model_fields_set and is_placeholder_secret(self.secret_key):
                insecure.append("SECRET_KEY")
            if admin_password and is_placeholder_secret(admin_password):
                insecure.append("INITIAL_ADMIN_PASSWORD")
            if len(ingest_secret) < 32 or is_placeholder_secret(ingest_secret):
                insecure.append("OBSERVABILITY_INGEST_SECRET (ingest disabled until configured)")
            if insecure:
                logger.warning(
                    "Development configuration contains placeholder or missing secrets: %s. "
                    "Replace them before exposing this service.",
                    ", ".join(insecure),
                )

        return self


settings = Settings()
