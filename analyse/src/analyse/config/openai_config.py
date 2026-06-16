from __future__ import annotations

from dataclasses import dataclass

from analyse.config.settings import Settings, get_settings


@dataclass(frozen=True)
class OpenAIConfig:
    """Cau hinh toi thieu de tich hop OpenAI trong giai doan sau."""

    api_key: str | None
    model: str
    temperature: float
    timeout_ms: int

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_openai_api_key_here")


def get_openai_config(settings: Settings | None = None) -> OpenAIConfig:
    settings = settings or get_settings()
    return OpenAIConfig(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        timeout_ms=settings.openai_timeout_ms,
    )
