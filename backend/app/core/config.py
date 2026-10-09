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
    cors_origins: str = "http://localhost:3000,http://localhost:5173"


settings = Settings()