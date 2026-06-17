from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cau hinh runtime cho service analyse."""

    node_env: str = Field(default="development", alias="NODE_ENV")
    analyse_host: str = Field(default="0.0.0.0", alias="ANALYSE_HOST")
    analyse_port: int = Field(default=5100, alias="ANALYSE_PORT")

    backend_api_url: str = Field(default="http://localhost:5000", alias="BACKEND_API_URL")
    backend_api_token: Optional[str] = Field(default=None, alias="BACKEND_API_TOKEN")

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.2, alias="OPENAI_TEMPERATURE")
    openai_timeout_ms: int = Field(default=60000, alias="OPENAI_TIMEOUT_MS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
