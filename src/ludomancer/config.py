from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    steam_api_key: str = Field(
        min_length=1,
        validation_alias=AliasChoices("STEAM_API_KEY", "steam_api_key"),
    )
    steam_id64: str = Field(
        min_length=1,
        validation_alias=AliasChoices("STEAM_ID64", "steam_id64"),
    )
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"),
    )
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"),
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-5",
        validation_alias=AliasChoices("ANTHROPIC_MODEL", "anthropic_model"),
    )
    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        validation_alias=AliasChoices("OPENROUTER_MODEL", "openrouter_model"),
    )
    cache_db_path: Path = Field(
        default=Path("cache.db"),
        validation_alias=AliasChoices("CACHE_DB_PATH", "cache_db_path"),
    )
    http_timeout_s: float = Field(
        default=15.0,
        validation_alias=AliasChoices("HTTP_TIMEOUT_S", "http_timeout_s"),
    )

    @field_validator("steam_api_key", "steam_id64")
    @classmethod
    def _strip_required_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
