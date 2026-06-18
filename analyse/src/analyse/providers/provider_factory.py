from __future__ import annotations

from analyse.config.settings import Settings, get_settings
from analyse.providers.base import BaseLLMProvider
from analyse.providers.gemini_provider import GeminiProvider
from analyse.providers.openai_provider import OpenAIProvider
from analyse.schemas.common import ProviderName


def get_llm_provider(provider: ProviderName, settings: Settings | None = None) -> BaseLLMProvider:
    settings = settings or get_settings()
    if provider == "gemini":
        return GeminiProvider(settings)
    if provider == "openai":
        return OpenAIProvider(settings)
    raise ValueError(f"Unsupported provider: {provider}")
