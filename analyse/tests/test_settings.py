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


def test_settings_support_report_export_and_research_variables():
    settings = Settings(
        REPORT_OUTPUT_DIR="custom_reports",
        REPORT_WRITE_MARKDOWN=False,
        REPORT_WRITE_HTML=True,
        REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE=False,
        REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=True,
        ENABLE_EXTERNAL_RESEARCH=True,
        ENABLE_VIETSTOCK=True,
        ENABLE_CAFEF=True,
        ENABLE_GOOGLE_NEWS_RSS=True,
        RESEARCH_USER_AGENT="pytest-agent",
        RESEARCH_GOOGLE_NEWS_RSS_ENABLED=True,
        RESEARCH_SOURCE_PRIORITY="cafef.vn,vietstock.vn",
    )

    assert settings.report_output_dir == "custom_reports"
    assert settings.report_write_markdown is False
    assert settings.report_write_html is True
    assert settings.report_include_markdown_content_in_response is False
    assert settings.report_include_html_content_in_response is True
    assert settings.enable_external_research is True
    assert settings.enable_vietstock is True
    assert settings.enable_cafef is True
    assert settings.enable_google_news_rss is True
    assert settings.research_user_agent == "pytest-agent"
    assert settings.research_google_news_rss_enabled is True
    assert settings.research_source_priority == "cafef.vn,vietstock.vn"


def test_settings_support_backend_analysis_data_and_scoring_variables():
    settings = Settings(
        BACKEND_API_AUTH_SCHEME="Token",
        BACKEND_USE_ANALYSIS_DATA_ENDPOINT=True,
        BACKEND_ANALYSIS_DATA_ENDPOINT="/api/stocks/{symbol}/analysis-data",
        BACKEND_ANALYSIS_DATA_QUARTERS=8,
        BACKEND_ANALYSIS_DATA_CHART_RANGE="6m",
        BACKEND_ANALYSIS_DATA_INCLUDE_PEERS=False,
        BACKEND_ANALYSIS_DATA_INCLUDE_MARKET_CONTEXT=False,
        BACKEND_STOCK_CHART_ENDPOINT="/api/stocks/{symbol}/chart",
        BACKEND_WATCHLIST_REQUIRED=True,
        ENABLE_SCORING=True,
        SCORING_MIN_FINANCIAL_PERIODS=4,
        SCORING_REQUIRE_FINANCIALS_FOR_OVERALL=True,
        SCORING_ENABLE_MARKET_CONTEXT=False,
        SCORING_ENABLE_PEER_CONTEXT=False,
    )

    assert settings.backend_api_auth_scheme == "Token"
    assert settings.backend_use_analysis_data_endpoint is True
    assert settings.backend_analysis_data_endpoint == "/api/stocks/{symbol}/analysis-data"
    assert settings.backend_analysis_data_quarters == 8
    assert settings.backend_analysis_data_chart_range == "6m"
    assert settings.backend_analysis_data_include_peers is False
    assert settings.backend_analysis_data_include_market_context is False
    assert settings.backend_stock_chart_endpoint == "/api/stocks/{symbol}/chart"
    assert settings.backend_watchlist_required is True
    assert settings.enable_scoring is True
    assert settings.scoring_min_financial_periods == 4
    assert settings.scoring_require_financials_for_overall is True
    assert settings.scoring_enable_market_context is False
    assert settings.scoring_enable_peer_context is False
