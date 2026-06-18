import pytest

from analyse.config.settings import Settings
from analyse.providers.gemini_provider import GeminiProvider
from analyse.providers.openai_provider import OpenAIProvider
from analyse.providers.provider_factory import get_llm_provider


def test_provider_factory_returns_openai():
    provider = get_llm_provider("openai", Settings())
    assert isinstance(provider, OpenAIProvider)


def test_provider_factory_returns_gemini():
    provider = get_llm_provider("gemini", Settings())
    assert isinstance(provider, GeminiProvider)


def test_provider_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_llm_provider("unknown", Settings())  # type: ignore[arg-type]
