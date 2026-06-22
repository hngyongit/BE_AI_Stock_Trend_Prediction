from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from analyse.schemas.common import ProviderName


class Settings(BaseSettings):
    """Cấu hình runtime cho analyse service."""

    analyse_env: str = Field(default="development", alias="ANALYSE_ENV")
    analyse_host: str = Field(default="0.0.0.0", alias="ANALYSE_HOST")
    analyse_port: int = Field(default=5100, alias="ANALYSE_PORT")
    analyse_log_level: str = Field(default="INFO", alias="ANALYSE_LOG_LEVEL")
    analyse_timezone: str = Field(default="Asia/Ho_Chi_Minh", alias="ANALYSE_TIMEZONE")
    pythonpath: str = Field(default="src", alias="PYTHONPATH")

    backend_api_base_url: str = Field(default="http://localhost:5000", alias="BACKEND_API_BASE_URL")
    backend_api_timeout_ms: int = Field(default=30000, alias="BACKEND_API_TIMEOUT_MS")
    backend_api_token: str | None = Field(default=None, alias="BACKEND_API_TOKEN")
    backend_api_auth_scheme: str = Field(default="Bearer", alias="BACKEND_API_AUTH_SCHEME")
    backend_use_analysis_data_endpoint: bool = Field(default=True, alias="BACKEND_USE_ANALYSIS_DATA_ENDPOINT")
    backend_analysis_data_endpoint: str = Field(default="/api/stocks/{symbol}/analysis-data", alias="BACKEND_ANALYSIS_DATA_ENDPOINT")
    backend_analysis_data_quarters: int = Field(default=6, alias="BACKEND_ANALYSIS_DATA_QUARTERS")
    backend_analysis_data_chart_range: str = Field(default="3m", alias="BACKEND_ANALYSIS_DATA_CHART_RANGE")
    backend_analysis_data_include_peers: bool = Field(default=True, alias="BACKEND_ANALYSIS_DATA_INCLUDE_PEERS")
    backend_analysis_data_include_market_context: bool = Field(default=True, alias="BACKEND_ANALYSIS_DATA_INCLUDE_MARKET_CONTEXT")
    backend_watchlist_endpoint: str = Field(default="/api/watchlists", alias="BACKEND_WATCHLIST_ENDPOINT")
    backend_watchlist_required: bool = Field(default=False, alias="BACKEND_WATCHLIST_REQUIRED")
    backend_stock_detail_endpoint: str = Field(default="/api/stocks/{symbol}", alias="BACKEND_STOCK_DETAIL_ENDPOINT")
    backend_stock_chart_endpoint: str = Field(default="/api/stocks/{symbol}/chart", alias="BACKEND_STOCK_CHART_ENDPOINT")

    report_output_dir: str = Field(default="reports", alias="REPORT_OUTPUT_DIR")
    report_write_markdown: bool = Field(default=True, alias="REPORT_WRITE_MARKDOWN")
    report_write_html: bool = Field(default=True, alias="REPORT_WRITE_HTML")
    report_include_markdown_content_in_response: bool = Field(default=True, alias="REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE")
    report_include_html_content_in_response: bool = Field(default=False, alias="REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE")
    report_language: str = Field(default="vi", alias="REPORT_LANGUAGE")
    summary_schema_version: str = Field(default="1.0", alias="SUMMARY_SCHEMA_VERSION")
    max_watchlist_symbols: int = Field(default=5, alias="MAX_WATCHLIST_SYMBOLS")
    analyse_one_symbol_only: bool = Field(default=True, alias="ANALYSE_ONE_SYMBOL_ONLY")

    default_llm_provider: ProviderName = Field(default="openai", alias="DEFAULT_LLM_PROVIDER")
    allow_request_model_override: bool = Field(default=True, alias="ALLOW_REQUEST_MODEL_OVERRIDE")

    enable_external_research: bool = Field(default=True, alias="ENABLE_EXTERNAL_RESEARCH")
    enable_vietstock: bool = Field(default=True, alias="ENABLE_VIETSTOCK")
    enable_cafef: bool = Field(default=True, alias="ENABLE_CAFEF")
    enable_google_news_rss: bool = Field(default=True, alias="ENABLE_GOOGLE_NEWS_RSS")
    research_cache_dir: str = Field(default=".research_cache", alias="RESEARCH_CACHE_DIR")
    research_cache_ttl_seconds: int = Field(default=21600, alias="RESEARCH_CACHE_TTL_SECONDS")
    research_timeout_ms: int = Field(default=20000, alias="RESEARCH_TIMEOUT_MS")
    max_research_items: int = Field(default=10, alias="MAX_RESEARCH_ITEMS")
    research_user_agent: str = Field(default="Mozilla/5.0 analyse-service/1.0", alias="RESEARCH_USER_AGENT")
    research_google_news_rss_enabled: bool = Field(default=True, alias="RESEARCH_GOOGLE_NEWS_RSS_ENABLED")
    research_max_article_age_days: int = Field(default=730, alias="RESEARCH_MAX_ARTICLE_AGE_DAYS")
    research_source_priority: str = Field(
        default="vietstock.vn,cafef.vn,tinnhanhchungkhoan.vn,vneconomy.vn,bnews.vn",
        alias="RESEARCH_SOURCE_PRIORITY",
    )

    default_capital_vnd: int = Field(default=100_000_000, alias="DEFAULT_CAPITAL_VND")
    default_risk_per_trade_pct: float = Field(default=1.0, alias="DEFAULT_RISK_PER_TRADE_PCT")
    default_max_position_pct: float = Field(default=12.0, alias="DEFAULT_MAX_POSITION_PCT")

    enable_scoring: bool = Field(default=True, alias="ENABLE_SCORING")
    scoring_min_financial_periods: int = Field(default=3, alias="SCORING_MIN_FINANCIAL_PERIODS")
    scoring_require_financials_for_overall: bool = Field(default=False, alias="SCORING_REQUIRE_FINANCIALS_FOR_OVERALL")
    scoring_enable_market_context: bool = Field(default=True, alias="SCORING_ENABLE_MARKET_CONTEXT")
    scoring_enable_peer_context: bool = Field(default=True, alias="SCORING_ENABLE_PEER_CONTEXT")

    gemini_enabled: bool = Field(default=True, alias="GEMINI_ENABLED")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    gemini_temperature: float = Field(default=0.2, alias="GEMINI_TEMPERATURE")
    gemini_top_p: float = Field(default=0.9, alias="GEMINI_TOP_P")
    gemini_max_output_tokens: int = Field(default=8192, alias="GEMINI_MAX_OUTPUT_TOKENS")
    gemini_timeout_ms: int = Field(default=60000, alias="GEMINI_TIMEOUT_MS")
    gemini_json_mode: bool = Field(default=True, alias="GEMINI_JSON_MODE")

    openai_enabled: bool = Field(default=True, alias="OPENAI_ENABLED")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.2, alias="OPENAI_TEMPERATURE")
    openai_max_output_tokens: int = Field(default=8192, alias="OPENAI_MAX_OUTPUT_TOKENS")
    openai_timeout_ms: int = Field(default=60000, alias="OPENAI_TIMEOUT_MS")
    openai_json_mode: bool = Field(default=True, alias="OPENAI_JSON_MODE")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
