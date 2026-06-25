from analyse.config.settings import Settings
from analyse.services.config_diagnostic_service import ConfigDiagnosticService

import asyncio


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
        REPORT_CHART_ENGINE="echarts",
        REPORT_CHART_ASSET_MODE="local",
        REPORT_CHART_ASSET_DIR="reports/assets",
        REPORT_ECHARTS_LOCAL_FILE="echarts.min.js",
        REPORT_CHART_FALLBACK="inline_svg",
        REPORT_CHART_ALLOW_CDN=False,
        REPORT_ECHARTS_CDN_URL="",
        ENABLE_EXTERNAL_RESEARCH=True,
        ENABLE_VIETSTOCK=True,
        ENABLE_CAFEF=True,
        ENABLE_GOOGLE_NEWS_RSS=True,
        RESEARCH_USER_AGENT="pytest-agent",
        RESEARCH_GOOGLE_NEWS_RSS_ENABLED=True,
        RESEARCH_SOURCE_PRIORITY="cafef.vn,vietstock.vn",
        RESEARCH_OFFICIAL_SOURCE_PRIORITY="hsx.vn,hnx.vn,ssc.gov.vn",
        ENABLE_SOURCE_BACKED_RESEARCH=True,
        ENABLE_DEEP_RESEARCH_CRAWL=True,
        SOURCE_BACKED_RESEARCH_TIMEOUT_MS=45000,
        SOURCE_BACKED_RESEARCH_MAX_ARTICLES=20,
        SOURCE_BACKED_RESEARCH_MAX_SOURCES_PER_SYMBOL=12,
        SOURCE_BACKED_RESEARCH_MAX_CRAWL_DEPTH=1,
        SOURCE_BACKED_RESEARCH_CACHE_TTL_SECONDS=21600,
        SOURCE_BACKED_RESEARCH_REQUIRE_SOURCE_FOR_NUMERIC_FACTS=True,
        GOOGLE_NEWS_RSS_MAX_ITEMS=15,
        GOOGLE_NEWS_RSS_LANGUAGE="vi",
        GOOGLE_NEWS_RSS_COUNTRY="VN",
        ENABLE_FORECAST_SCENARIOS=True,
        FORECAST_TIME_HORIZONS="short_term,base_term,medium_term",
        FORECAST_SCENARIO_COUNT=3,
        FORECAST_REQUIRE_TRIGGER_AND_INVALIDATION=True,
        FORECAST_ALLOW_PROBABILISTIC_LANGUAGE=True,
        FORECAST_DEFAULT_PROBABILITY_METHOD="score_weighted",
    )

    assert settings.report_output_dir == "custom_reports"
    assert settings.report_write_markdown is False
    assert settings.report_write_html is True
    assert settings.report_include_markdown_content_in_response is False
    assert settings.report_include_html_content_in_response is True
    assert settings.report_chart_engine == "echarts"
    assert settings.report_chart_asset_mode == "local"
    assert settings.report_chart_asset_dir == "reports/assets"
    assert settings.report_echarts_local_file == "echarts.min.js"
    assert settings.report_chart_fallback == "inline_svg"
    assert settings.report_chart_allow_cdn is False
    assert settings.report_echarts_cdn_url == ""
    assert settings.enable_external_research is True
    assert settings.enable_vietstock is True
    assert settings.enable_cafef is True
    assert settings.enable_google_news_rss is True
    assert settings.research_user_agent == "pytest-agent"
    assert settings.research_google_news_rss_enabled is True
    assert settings.research_source_priority == "cafef.vn,vietstock.vn"
    assert settings.research_official_source_priority == "hsx.vn,hnx.vn,ssc.gov.vn"
    assert settings.enable_source_backed_research is True
    assert settings.enable_deep_research_crawl is True
    assert settings.source_backed_research_timeout_ms == 45000
    assert settings.source_backed_research_max_articles == 20
    assert settings.source_backed_research_max_sources_per_symbol == 12
    assert settings.source_backed_research_max_crawl_depth == 1
    assert settings.source_backed_research_cache_ttl_seconds == 21600
    assert settings.source_backed_research_require_source_for_numeric_facts is True
    assert settings.google_news_rss_max_items == 15
    assert settings.google_news_rss_language == "vi"
    assert settings.google_news_rss_country == "VN"
    assert settings.enable_forecast_scenarios is True
    assert settings.forecast_time_horizons == "short_term,base_term,medium_term"
    assert settings.forecast_scenario_count == 3
    assert settings.forecast_require_trigger_and_invalidation is True
    assert settings.forecast_allow_probabilistic_language is True
    assert settings.forecast_default_probability_method == "score_weighted"


def test_settings_support_canonical_env_aliases_and_env_file_path():
    settings = Settings(
        LOG_LEVEL="DEBUG",
        TIMEZONE="Asia/Ho_Chi_Minh",
        CORS_ALLOWED_ORIGINS=" http://localhost:5173, http://127.0.0.1:5173, ",
        CORS_ALLOW_CREDENTIALS=True,
        REPORT_RENDER_MARKDOWN=False,
        REPORT_RENDER_HTML=True,
        BACKEND_API_VERIFY_SSL=False,
        PLAYWRIGHT_HEADLESS=False,
        PLAYWRIGHT_VIEWPORT_WIDTH=1280,
        PLAYWRIGHT_VIEWPORT_HEIGHT=720,
        PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=45000,
        PLAYWRIGHT_EXTRA_WAIT_MS=1500,
        PLAYWRIGHT_WAIT_UNTIL="domcontentloaded",
        PLAYWRIGHT_RETRY_COUNT=2,
        PLAYWRIGHT_RETRY_BACKOFF_MS=1500,
    )

    assert settings.analyse_log_level == "DEBUG"
    assert settings.analyse_timezone == "Asia/Ho_Chi_Minh"
    assert settings.cors_allowed_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.effective_cors_allow_credentials is True
    assert settings.report_write_markdown is False
    assert settings.report_write_html is True
    assert settings.backend_api_verify_ssl is False
    assert settings.playwright_headless is False
    assert settings.playwright_viewport_width == 1280
    assert settings.playwright_viewport_height == 720
    assert settings.playwright_navigation_timeout_ms == 45000
    assert settings.playwright_extra_wait_ms == 1500
    assert settings.playwright_wait_until == "domcontentloaded"
    assert settings.playwright_retry_count == 2
    assert settings.playwright_retry_backoff_ms == 1500
    assert settings.env_file_path.endswith("analyse\\.env") or settings.env_file_path.endswith("analyse/.env")


def test_settings_disables_cors_credentials_for_wildcard_origin():
    settings = Settings(CORS_ALLOWED_ORIGINS="*", CORS_ALLOW_CREDENTIALS=True)

    assert settings.cors_allowed_origin_list == ["*"]
    assert settings.effective_cors_allow_credentials is False


def test_env_example_documents_cors_variables():
    content = (Settings().env_file_path.replace(".env", ".env.example"))
    with open(content, encoding="utf-8") as handle:
        text = handle.read()

    assert "CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173" in text
    assert "CORS_ALLOW_CREDENTIALS=true" in text


def test_cafef_financial_timeout_default_override_and_invalid_fallback():
    assert Settings(_env_file=None).cafef_financial_timeout_ms == 90000
    assert Settings(_env_file=None, CAFEF_FINANCIAL_TIMEOUT_MS=123456).cafef_financial_timeout_ms == 123456
    assert Settings(_env_file=None, CAFEF_FINANCIAL_TIMEOUT_MS="not-a-number").cafef_financial_timeout_ms == 90000


def test_config_check_masks_secrets():
    settings = Settings(
        BACKEND_API_TOKEN="secret-token",
        OPENAI_API_KEY="sk-secret",
        GEMINI_API_KEY="gemini-secret",
        AI_REPORT_DB_URL="mssql+pyodbc://user:sql-secret@localhost:1433/AIStockAnalysis?driver=ODBC+Driver+18+for+SQL+Server",
        BACKEND_API_BASE_URL="http://localhost:5000/api",
    )

    data = asyncio.run(ConfigDiagnosticService(settings).build(check_backend=False))

    assert data["backend"]["base_url"] == "http://localhost:5000"
    assert data["backend"]["env_token_deprecated"] == "set"
    assert data["backend"]["request_auth"] == "required_via_authorization_header"
    assert data["providers"]["openai"] == "configured"
    assert data["providers"]["gemini"] == "configured"
    assert data["history"]["db_url"] == "set"
    assert data["history"]["db_url_safe_for_log"]
    assert "sql-secret" not in str(data["history"]["db_url_safe_for_log"])
    assert "secret-token" not in str(data)
    assert "sk-secret" not in str(data)
    assert "sql-secret" not in str(data)


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
        BACKEND_CURRENT_USER_ENDPOINT="/api/users/me",
        BACKEND_WATCHLIST_REQUIRED=True,
        ENABLE_AI_REPORT_HISTORY=True,
        AI_REPORT_DB_URL="mssql+pyodbc://user:password@localhost:1433/AIStockAnalysis?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
        AI_REPORT_HISTORY_SAVE_FAILURE_POLICY="strict",
        REPORT_MISSING_VALUE_POLICY="source_backed_then_model_inference",
        REPORT_ALLOW_MODEL_INFERENCE_FOR_QUALITATIVE_FIELDS=True,
        REPORT_SHOW_MISSING_REASON=True,
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
    assert settings.backend_current_user_endpoint == "/api/users/me"
    assert settings.backend_watchlist_required is True
    assert settings.enable_ai_report_history is True
    assert settings.ai_report_db_url.startswith("mssql+pyodbc://")
    assert settings.ai_report_history_save_failure_policy == "strict"
    assert settings.report_missing_value_policy == "source_backed_then_model_inference"
    assert settings.report_allow_model_inference_for_qualitative_fields is True
    assert settings.report_show_missing_reason is True
    assert settings.enable_scoring is True
    assert settings.scoring_min_financial_periods == 4
    assert settings.scoring_require_financials_for_overall is True
    assert settings.scoring_enable_market_context is False
    assert settings.scoring_enable_peer_context is False


def test_settings_support_vietstock_bctc_aliases_and_peer_fallback():
    settings = Settings(
        ENABLE_CAFEF_COMPANY_FALLBACK=True,
        CAFEF_COMPANY_URL_TEMPLATE="https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn",
        CAFEF_COMPANY_TIMEOUT_MS=33000,
        CAFEF_COMPANY_CACHE_TTL_SECONDS=300,
        CAFEF_COMPANY_USE_BROWSER_FALLBACK=False,
        ENABLE_CAFEF_FINANCIAL_FALLBACK=True,
        CAFEF_FINANCIAL_URL_TEMPLATE="https://cafef.vn/du-lieu/{exchange}/{symbol}-tai-chinh.chn",
        CAFEF_FINANCIAL_TIMEOUT_MS=34000,
        CAFEF_FINANCIAL_CACHE_TTL_SECONDS=400,
        CAFEF_FINANCIAL_MAX_PERIODS=5,
        CAFEF_FINANCIAL_UNIT="Triệu đồng",
        CAFEF_FINANCIAL_USE_BROWSER_FALLBACK=False,
        ENABLE_VIETSTOCK_BCTC_FALLBACK=True,
        VIETSTOCK_BCTC_URL_TEMPLATE="https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT",
        VIETSTOCK_BCTC_TIMEOUT_MS=31000,
        VIETSTOCK_BCTC_CACHE_TTL_SECONDS=100,
        VIETSTOCK_BCTC_MAX_PERIODS=6,
        VIETSTOCK_BCTC_UNIT="Triệu đồng",
        VIETSTOCK_BCTC_USE_BROWSER_FALLBACK=False,
        VIETSTOCK_BCTC_BROWSER_HEADLESS=False,
        VIETSTOCK_BCTC_BROWSER_WAIT_UNTIL="load",
        VIETSTOCK_BCTC_BROWSER_WAIT_SELECTOR="table",
        VIETSTOCK_BCTC_BROWSER_EXTRA_WAIT_MS=1200,
        VIETSTOCK_BCTC_BROWSER_VIEWPORT_WIDTH=1440,
        VIETSTOCK_BCTC_BROWSER_VIEWPORT_HEIGHT=900,
        ENABLE_VIETSTOCK_PEER_FALLBACK=True,
        VIETSTOCK_PEER_URL_TEMPLATE="https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm",
        VIETSTOCK_PEER_TIMEOUT_MS=32000,
        VIETSTOCK_PEER_CACHE_TTL_SECONDS=200,
        VIETSTOCK_PEER_MAX_ITEMS=7,
        VIETSTOCK_PEER_USE_BROWSER_FALLBACK=False,
        VIETSTOCK_PEER_DEFAULT_TAB="Tổng quan",
        ENABLE_PEER_WEB_ENRICHMENT=True,
        PEER_WEB_ENRICHMENT_MAX_PEERS=10,
        PEER_WEB_ENRICHMENT_TIMEOUT_MS=30000,
        PEER_RECOMMENDATION_TOP_N=5,
        EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML=True,
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        VIETSTOCK_DEBUG_SAVE_RENDERED_HTML=True,
        VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=True,
        REPORT_MARKET_CHART_TYPE="segmented_bar",
    )

    assert settings.enable_cafef_company_fallback is True
    assert settings.cafef_company_url_template.endswith("{symbol}-ban-lanh-dao-so-huu.chn")
    assert settings.cafef_company_timeout_ms == 33000
    assert settings.cafef_company_cache_ttl_seconds == 300
    assert settings.cafef_company_use_browser_fallback is False
    assert settings.enable_cafef_financial_fallback is True
    assert settings.cafef_financial_url_template.endswith("{symbol}-tai-chinh.chn")
    assert settings.cafef_financial_timeout_ms == 34000
    assert settings.cafef_financial_cache_ttl_seconds == 400
    assert settings.cafef_financial_max_periods == 5
    assert settings.cafef_financial_unit == "Triệu đồng"
    assert settings.cafef_financial_use_browser_fallback is False
    assert settings.effective_enable_vietstock_financial_fallback is True
    assert settings.effective_vietstock_financial_url_template.endswith("tab=BCTT")
    assert settings.effective_vietstock_financial_timeout_ms == 31000
    assert settings.effective_vietstock_financial_cache_ttl_seconds == 100
    assert settings.effective_vietstock_financial_max_periods == 6
    assert settings.effective_vietstock_financial_unit == "Triệu đồng"
    assert settings.effective_vietstock_financial_use_browser_fallback is False
    assert settings.effective_vietstock_financial_browser_headless is False
    assert settings.effective_vietstock_financial_browser_wait_until == "load"
    assert settings.effective_vietstock_financial_browser_wait_selector == "table"
    assert settings.effective_vietstock_financial_browser_extra_wait_ms == 1200
    assert settings.effective_vietstock_financial_browser_viewport_width == 1440
    assert settings.effective_vietstock_financial_browser_viewport_height == 900
    assert settings.enable_vietstock_peer_fallback is True
    assert settings.vietstock_peer_url_template.endswith("so-sanh-gia-co-phieu-cung-nganh.htm")
    assert settings.vietstock_peer_timeout_ms == 32000
    assert settings.vietstock_peer_cache_ttl_seconds == 200
    assert settings.vietstock_peer_max_items == 7
    assert settings.vietstock_peer_use_browser_fallback is False
    assert settings.vietstock_peer_default_tab == "Tổng quan"
    assert settings.enable_peer_web_enrichment is True
    assert settings.peer_web_enrichment_max_peers == 10
    assert settings.peer_web_enrichment_timeout_ms == 30000
    assert settings.peer_recommendation_top_n == 5
    assert settings.external_data_debug_save_rendered_html is True
    assert settings.external_data_debug_save_extraction_json is True
    assert settings.vietstock_debug_save_rendered_html is True
    assert settings.vietstock_debug_save_extraction_json is True
    assert settings.report_market_chart_type == "segmented_bar"
