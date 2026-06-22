from analyse.config.settings import Settings


def test_settings_support_llm_selection_variables():
    settings = Settings(
        DEFAULT_LLM_PROVIDER="gemini",
        ALLOW_REQUEST_MODEL_OVERRIDE=False,
        OPENAI_MODEL="gpt-env",
        GEMINI_MODEL="gemini-env",
    )

    assert settings.default_llm_provider == "gemini"
    assert settings.allow_request_model_override is False
    assert settings.openai_model == "gpt-env"
    assert settings.gemini_model == "gemini-env"
