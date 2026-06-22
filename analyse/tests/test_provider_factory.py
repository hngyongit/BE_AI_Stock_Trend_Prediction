import pytest

from analyse.config.settings import Settings
from analyse.providers.gemini_provider import GeminiProvider
from analyse.providers.openai_provider import OpenAIProvider
from analyse.providers.provider_factory import get_llm_provider


def test_provider_factory_returns_openai():
    provider = get_llm_provider("openai", Settings(OPENAI_MODEL="gpt-env"))
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-env"


def test_provider_factory_returns_gemini():
    provider = get_llm_provider("gemini", Settings(GEMINI_MODEL="gemini-env"))
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-env"


def test_provider_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_llm_provider("unknown", Settings())  # type: ignore[arg-type]


def test_provider_factory_applies_request_level_model_override():
    provider = get_llm_provider("openai", Settings(OPENAI_MODEL="gpt-env"), model="gpt-request")
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-request"
