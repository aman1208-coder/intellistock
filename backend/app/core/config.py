import secrets
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://postgres:postgres@localhost:5432/intellistock"
    secret_key: str = secrets.token_urlsafe(32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    initial_admin_password: Optional[SecretStr] = None
    allow_public_registration: bool = False
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


settings = Settings()
