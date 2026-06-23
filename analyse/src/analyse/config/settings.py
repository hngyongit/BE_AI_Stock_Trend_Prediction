from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from analyse.schemas.common import ProviderName


ANALYSE_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Cấu hình runtime cho analyse service."""

    analyse_env: str = Field(default="development", alias="ANALYSE_ENV")
    analyse_host: str = Field(default="0.0.0.0", alias="ANALYSE_HOST")
    analyse_port: int = Field(default=5100, alias="ANALYSE_PORT")
    analyse_log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL", "ANALYSE_LOG_LEVEL"))
    analyse_timezone: str = Field(default="Asia/Ho_Chi_Minh", validation_alias=AliasChoices("TIMEZONE", "ANALYSE_TIMEZONE"))
    pythonpath: str = Field(default="src", alias="PYTHONPATH")
    cors_allowed_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", alias="CORS_ALLOWED_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")

    backend_api_base_url: str = Field(
        default="http://localhost:5000",
        validation_alias=AliasChoices("BACKEND_API_BASE_URL", "BACKEND_API_URL", "BACKEND_BASE_URL", "API_BASE_URL"),
    )
    backend_api_timeout_ms: int = Field(default=30000, alias="BACKEND_API_TIMEOUT_MS")
    backend_api_verify_ssl: bool = Field(default=True, alias="BACKEND_API_VERIFY_SSL")
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
    report_write_markdown: bool = Field(default=True, validation_alias=AliasChoices("REPORT_RENDER_MARKDOWN", "REPORT_WRITE_MARKDOWN"))
    report_write_html: bool = Field(default=True, validation_alias=AliasChoices("REPORT_RENDER_HTML", "REPORT_WRITE_HTML"))
    report_include_markdown_content_in_response: bool = Field(default=True, alias="REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE")
    report_include_html_content_in_response: bool = Field(default=False, alias="REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE")
    report_language: str = Field(default="vi", alias="REPORT_LANGUAGE")
    report_chart_engine: str = Field(default="echarts", alias="REPORT_CHART_ENGINE")
    report_chart_asset_mode: str = Field(default="local", alias="REPORT_CHART_ASSET_MODE")
    report_chart_asset_dir: str = Field(default="reports/assets", alias="REPORT_CHART_ASSET_DIR")
    report_echarts_local_file: str = Field(default="echarts.min.js", alias="REPORT_ECHARTS_LOCAL_FILE")
    report_chart_fallback: str = Field(default="inline_svg", alias="REPORT_CHART_FALLBACK")
    report_chart_allow_cdn: bool = Field(default=False, alias="REPORT_CHART_ALLOW_CDN")
    report_echarts_cdn_url: str | None = Field(default=None, alias="REPORT_ECHARTS_CDN_URL")
    report_market_chart_type: str = Field(default="segmented_bar", alias="REPORT_MARKET_CHART_TYPE")
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

    enable_cafef_company_fallback: bool = Field(default=True, alias="ENABLE_CAFEF_COMPANY_FALLBACK")
    cafef_company_url_template: str = Field(
        default="https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn",
        alias="CAFEF_COMPANY_URL_TEMPLATE",
    )
    cafef_company_timeout_ms: int = Field(default=30000, alias="CAFEF_COMPANY_TIMEOUT_MS")
    cafef_company_cache_ttl_seconds: int = Field(default=21600, alias="CAFEF_COMPANY_CACHE_TTL_SECONDS")
    cafef_company_use_browser_fallback: bool = Field(default=True, alias="CAFEF_COMPANY_USE_BROWSER_FALLBACK")

    enable_cafef_financial_fallback: bool = Field(default=True, alias="ENABLE_CAFEF_FINANCIAL_FALLBACK")
    cafef_financial_url_template: str = Field(
        default="https://cafef.vn/du-lieu/{exchange}/{symbol}-tai-chinh.chn",
        alias="CAFEF_FINANCIAL_URL_TEMPLATE",
    )
    cafef_financial_timeout_ms: int = Field(default=90000, alias="CAFEF_FINANCIAL_TIMEOUT_MS")
    cafef_financial_cache_ttl_seconds: int = Field(default=21600, alias="CAFEF_FINANCIAL_CACHE_TTL_SECONDS")
    cafef_financial_max_periods: int = Field(default=8, alias="CAFEF_FINANCIAL_MAX_PERIODS")
    cafef_financial_unit: str = Field(default="Tỷ đồng", alias="CAFEF_FINANCIAL_UNIT")
    cafef_financial_use_browser_fallback: bool = Field(default=True, alias="CAFEF_FINANCIAL_USE_BROWSER_FALLBACK")

    enable_vietstock_financial_fallback: bool = Field(default=True, alias="ENABLE_VIETSTOCK_FINANCIAL_FALLBACK")
    enable_vietstock_bctc_fallback: bool | None = Field(default=None, alias="ENABLE_VIETSTOCK_BCTC_FALLBACK")
    vietstock_financial_url_template: str = Field(
        default="https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT",
        alias="VIETSTOCK_FINANCIAL_URL_TEMPLATE",
    )
    vietstock_bctc_url_template: str | None = Field(default=None, alias="VIETSTOCK_BCTC_URL_TEMPLATE")
    vietstock_financial_timeout_ms: int = Field(default=60000, alias="VIETSTOCK_FINANCIAL_TIMEOUT_MS")
    vietstock_bctc_timeout_ms: int | None = Field(default=None, alias="VIETSTOCK_BCTC_TIMEOUT_MS")
    vietstock_financial_cache_ttl_seconds: int = Field(default=21600, alias="VIETSTOCK_FINANCIAL_CACHE_TTL_SECONDS")
    vietstock_bctc_cache_ttl_seconds: int | None = Field(default=None, alias="VIETSTOCK_BCTC_CACHE_TTL_SECONDS")
    vietstock_financial_max_periods: int = Field(default=8, alias="VIETSTOCK_FINANCIAL_MAX_PERIODS")
    vietstock_bctc_max_periods: int | None = Field(default=None, alias="VIETSTOCK_BCTC_MAX_PERIODS")
    vietstock_financial_unit: str = Field(default="Tỷ đồng", alias="VIETSTOCK_FINANCIAL_UNIT")
    vietstock_bctc_unit: str | None = Field(default=None, alias="VIETSTOCK_BCTC_UNIT")
    vietstock_financial_use_browser_fallback: bool = Field(default=True, alias="VIETSTOCK_FINANCIAL_USE_BROWSER_FALLBACK")
    vietstock_bctc_use_browser_fallback: bool | None = Field(default=None, alias="VIETSTOCK_BCTC_USE_BROWSER_FALLBACK")
    vietstock_financial_browser_headless: bool = Field(default=True, alias="VIETSTOCK_FINANCIAL_BROWSER_HEADLESS")
    vietstock_bctc_browser_headless: bool | None = Field(default=None, alias="VIETSTOCK_BCTC_BROWSER_HEADLESS")
    vietstock_financial_browser_wait_until: str = Field(default="domcontentloaded", alias="VIETSTOCK_FINANCIAL_BROWSER_WAIT_UNTIL")
    vietstock_bctc_browser_wait_until: str | None = Field(default=None, alias="VIETSTOCK_BCTC_BROWSER_WAIT_UNTIL")
    vietstock_financial_browser_wait_selector: str | None = Field(default=None, alias="VIETSTOCK_FINANCIAL_BROWSER_WAIT_SELECTOR")
    vietstock_bctc_browser_wait_selector: str | None = Field(default=None, alias="VIETSTOCK_BCTC_BROWSER_WAIT_SELECTOR")
    vietstock_financial_browser_extra_wait_ms: int = Field(default=5000, alias="VIETSTOCK_FINANCIAL_BROWSER_EXTRA_WAIT_MS")
    vietstock_bctc_browser_extra_wait_ms: int | None = Field(default=None, alias="VIETSTOCK_BCTC_BROWSER_EXTRA_WAIT_MS")
    vietstock_financial_browser_viewport_width: int = Field(default=1600, alias="VIETSTOCK_FINANCIAL_BROWSER_VIEWPORT_WIDTH")
    vietstock_bctc_browser_viewport_width: int | None = Field(default=None, alias="VIETSTOCK_BCTC_BROWSER_VIEWPORT_WIDTH")
    vietstock_financial_browser_viewport_height: int = Field(default=1100, alias="VIETSTOCK_FINANCIAL_BROWSER_VIEWPORT_HEIGHT")
    vietstock_bctc_browser_viewport_height: int | None = Field(default=None, alias="VIETSTOCK_BCTC_BROWSER_VIEWPORT_HEIGHT")

    enable_vietstock_peer_fallback: bool = Field(default=True, alias="ENABLE_VIETSTOCK_PEER_FALLBACK")
    vietstock_peer_url_template: str = Field(
        default="https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm",
        alias="VIETSTOCK_PEER_URL_TEMPLATE",
    )
    vietstock_peer_timeout_ms: int = Field(default=60000, alias="VIETSTOCK_PEER_TIMEOUT_MS")
    vietstock_peer_cache_ttl_seconds: int = Field(default=21600, alias="VIETSTOCK_PEER_CACHE_TTL_SECONDS")
    vietstock_peer_max_items: int = Field(default=10, alias="VIETSTOCK_PEER_MAX_ITEMS")
    vietstock_peer_use_browser_fallback: bool = Field(default=True, alias="VIETSTOCK_PEER_USE_BROWSER_FALLBACK")
    vietstock_peer_browser_headless: bool = Field(default=True, alias="VIETSTOCK_PEER_BROWSER_HEADLESS")
    vietstock_peer_browser_wait_until: str = Field(default="domcontentloaded", alias="VIETSTOCK_PEER_BROWSER_WAIT_UNTIL")
    vietstock_peer_browser_wait_selector: str | None = Field(default=None, alias="VIETSTOCK_PEER_BROWSER_WAIT_SELECTOR")
    vietstock_peer_browser_extra_wait_ms: int = Field(default=5000, alias="VIETSTOCK_PEER_BROWSER_EXTRA_WAIT_MS")
    vietstock_peer_browser_viewport_width: int = Field(default=1600, alias="VIETSTOCK_PEER_BROWSER_VIEWPORT_WIDTH")
    vietstock_peer_browser_viewport_height: int = Field(default=1100, alias="VIETSTOCK_PEER_BROWSER_VIEWPORT_HEIGHT")
    vietstock_peer_default_tab: str = Field(default="Tổng quan", alias="VIETSTOCK_PEER_DEFAULT_TAB")
    enable_peer_web_enrichment: bool = Field(default=True, alias="ENABLE_PEER_WEB_ENRICHMENT")
    peer_web_enrichment_max_peers: int = Field(default=10, alias="PEER_WEB_ENRICHMENT_MAX_PEERS")
    peer_web_enrichment_timeout_ms: int = Field(default=30000, alias="PEER_WEB_ENRICHMENT_TIMEOUT_MS")
    peer_recommendation_top_n: int = Field(default=5, alias="PEER_RECOMMENDATION_TOP_N")
    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    playwright_viewport_width: int = Field(default=1600, alias="PLAYWRIGHT_VIEWPORT_WIDTH")
    playwright_viewport_height: int = Field(default=1100, alias="PLAYWRIGHT_VIEWPORT_HEIGHT")
    playwright_navigation_timeout_ms: int = Field(default=60000, alias="PLAYWRIGHT_NAVIGATION_TIMEOUT_MS")
    playwright_extra_wait_ms: int = Field(default=4000, alias="PLAYWRIGHT_EXTRA_WAIT_MS")
    external_data_debug_save_rendered_html: bool = Field(default=False, alias="EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML")
    external_data_debug_save_extraction_json: bool = Field(default=False, alias="EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON")
    vietstock_debug_save_rendered_html: bool = Field(default=False, alias="VIETSTOCK_DEBUG_SAVE_RENDERED_HTML")
    vietstock_debug_save_extraction_json: bool = Field(default=False, alias="VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON")

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
        env_file=str(ANALYSE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("cafef_financial_timeout_ms", mode="before")
    @classmethod
    def _validate_cafef_financial_timeout_ms(cls, value: object) -> int:
        try:
            timeout_ms = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 90000
        return timeout_ms if timeout_ms > 0 else 90000

    @property
    def env_file_path(self) -> str:
        return str(ANALYSE_ROOT / ".env")

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in (self.cors_allowed_origins or "").split(",") if origin.strip()]
        if not origins:
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        if "*" in origins:
            return ["*"]
        return origins

    @property
    def effective_cors_allow_credentials(self) -> bool:
        if self.cors_allowed_origin_list == ["*"]:
            return False
        return self.cors_allow_credentials

    @property
    def effective_enable_vietstock_financial_fallback(self) -> bool:
        if self.enable_vietstock_bctc_fallback is False or self.enable_vietstock_financial_fallback is False:
            return False
        return self.enable_vietstock_bctc_fallback if self.enable_vietstock_bctc_fallback is not None else self.enable_vietstock_financial_fallback

    @property
    def effective_vietstock_financial_url_template(self) -> str:
        return self.vietstock_bctc_url_template or self.vietstock_financial_url_template

    @property
    def effective_vietstock_financial_timeout_ms(self) -> int:
        return self.vietstock_bctc_timeout_ms or self.vietstock_financial_timeout_ms

    @property
    def effective_vietstock_financial_cache_ttl_seconds(self) -> int:
        return self.vietstock_bctc_cache_ttl_seconds or self.vietstock_financial_cache_ttl_seconds

    @property
    def effective_vietstock_financial_max_periods(self) -> int:
        return self.vietstock_bctc_max_periods or self.vietstock_financial_max_periods

    @property
    def effective_vietstock_financial_unit(self) -> str:
        return self.vietstock_bctc_unit or self.vietstock_financial_unit

    @property
    def effective_vietstock_financial_use_browser_fallback(self) -> bool:
        if self.vietstock_bctc_use_browser_fallback is False or self.vietstock_financial_use_browser_fallback is False:
            return False
        return self.vietstock_bctc_use_browser_fallback if self.vietstock_bctc_use_browser_fallback is not None else self.vietstock_financial_use_browser_fallback

    @property
    def effective_vietstock_financial_browser_headless(self) -> bool:
        return self.vietstock_bctc_browser_headless if self.vietstock_bctc_browser_headless is not None else self.vietstock_financial_browser_headless

    @property
    def effective_vietstock_financial_browser_wait_until(self) -> str:
        wait_until = (self.vietstock_bctc_browser_wait_until or self.vietstock_financial_browser_wait_until or "domcontentloaded").strip().lower()
        return "domcontentloaded" if wait_until == "networkidle" else wait_until

    @property
    def effective_vietstock_financial_browser_wait_selector(self) -> str | None:
        return self.vietstock_bctc_browser_wait_selector or self.vietstock_financial_browser_wait_selector

    @property
    def effective_vietstock_financial_browser_extra_wait_ms(self) -> int:
        return self.vietstock_bctc_browser_extra_wait_ms if self.vietstock_bctc_browser_extra_wait_ms is not None else self.vietstock_financial_browser_extra_wait_ms

    @property
    def effective_vietstock_financial_browser_viewport_width(self) -> int:
        return self.vietstock_bctc_browser_viewport_width or self.vietstock_financial_browser_viewport_width

    @property
    def effective_vietstock_financial_browser_viewport_height(self) -> int:
        return self.vietstock_bctc_browser_viewport_height or self.vietstock_financial_browser_viewport_height


@lru_cache
def get_settings() -> Settings:
    return Settings()
