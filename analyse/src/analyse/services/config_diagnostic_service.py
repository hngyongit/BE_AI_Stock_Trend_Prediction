from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import httpx

from analyse.clients.backend_client import BackendClient
from analyse.config.settings import Settings, get_settings
from analyse.db.session import safe_db_url_for_log


LOGGER = logging.getLogger("analyse.config")


class ConfigDiagnosticService:
    """Tạo snapshot cấu hình đã mask secret để debug env/deploy."""

    def __init__(self, settings: Settings | None = None, backend_client: BackendClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.backend_client = backend_client or BackendClient(self.settings)

    async def build(self, *, check_backend: bool = False) -> dict[str, Any]:
        backend: dict[str, Any] = {
            "base_url": self.backend_client.base_url,
            "verify_ssl": self.settings.backend_api_verify_ssl,
            "timeout_ms": self.settings.backend_api_timeout_ms,
            "request_auth": "required_via_authorization_header",
            "env_token_deprecated": self._secret_status(self.settings.backend_api_token),
            "auth_scheme": self.settings.backend_api_auth_scheme or "none",
            "analysis_data_url_example": self.backend_client.build_stock_analysis_data_url(
                "HPG",
                exchange="HOSE",
                quarters=self.settings.backend_analysis_data_quarters,
                chart_range=self.settings.backend_analysis_data_chart_range,
                include_peers=self.settings.backend_analysis_data_include_peers,
                include_market_context=self.settings.backend_analysis_data_include_market_context,
            ),
            "reachable": "not_checked",
        }
        if check_backend:
            backend["reachable"] = await self._backend_reachable()

        return {
            "env_file": {
                "path": self.settings.env_file_path,
                "exists": Path(self.settings.env_file_path).exists(),
            },
            "app": {
                "env": self.settings.analyse_env,
                "host": self.settings.analyse_host,
                "port": self.settings.analyse_port,
                "log_level": self.settings.analyse_log_level,
                "timezone": self.settings.analyse_timezone,
            },
            "backend": backend,
            "providers": {
                "default": self.settings.default_llm_provider,
                "openai": "configured" if self.settings.openai_api_key else "missing_key",
                "gemini": "configured" if self.settings.gemini_api_key else "missing_key",
            },
            "external_sources": {
                "external_research": self._enabled(self.settings.enable_external_research),
                "google_news_rss": self._enabled(self.settings.enable_google_news_rss and self.settings.research_google_news_rss_enabled),
                "cafef_company": self._enabled(self.settings.enable_cafef_company_fallback),
                "cafef_financial": self._enabled(self.settings.enable_cafef_financial_fallback),
                "vietstock_bctc": self._enabled(self.settings.effective_enable_vietstock_financial_fallback),
                "vietstock_peer": self._enabled(self.settings.enable_vietstock_peer_fallback),
            },
            "playwright": self._playwright_status(),
            "reports": {
                "output_dir": self.settings.report_output_dir,
                "render_markdown": self.settings.report_write_markdown,
                "render_html": self.settings.report_write_html,
                "debug_rendered_html": self.settings.external_data_debug_save_rendered_html,
                "debug_extraction_json": self.settings.external_data_debug_save_extraction_json,
            },
            "history": {
                "enabled": self._enabled(self.settings.enable_ai_report_history),
                "db_url": self._secret_status(self.settings.ai_report_db_url),
                "db_url_safe_for_log": safe_db_url_for_log(self.settings.ai_report_db_url),
                "current_user_endpoint": self.settings.backend_current_user_endpoint,
                "save_failure_policy": self.settings.ai_report_history_save_failure_policy,
            },
        }

    def startup_snapshot(self) -> dict[str, Any]:
        return {
            "ANALYSE_PORT": self.settings.analyse_port,
            "BACKEND_API_BASE_URL": self.backend_client.base_url,
            "BACKEND_API_TOKEN_DEPRECATED": self._secret_status(self.settings.backend_api_token),
            "OPENAI_API_KEY": self._secret_status(self.settings.openai_api_key),
            "GEMINI_API_KEY": self._secret_status(self.settings.gemini_api_key),
            "ENABLE_CAFEF_COMPANY_FALLBACK": self.settings.enable_cafef_company_fallback,
            "ENABLE_CAFEF_FINANCIAL_FALLBACK": self.settings.enable_cafef_financial_fallback,
            "ENABLE_VIETSTOCK_PEER_FALLBACK": self.settings.enable_vietstock_peer_fallback,
            "ENABLE_AI_REPORT_HISTORY": self.settings.enable_ai_report_history,
            "PLAYWRIGHT_PACKAGE_AVAILABLE": self._playwright_status()["package"] == "available",
        }

    async def _backend_reachable(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3.0, verify=self.settings.backend_api_verify_ssl) as client:
                response = await client.get(self.backend_client.base_url)
            return {"status": "reachable", "http_status": response.status_code}
        except httpx.ConnectTimeout:
            return {"status": "failed", "category": "connect_timeout"}
        except httpx.ReadTimeout:
            return {"status": "failed", "category": "read_timeout"}
        except httpx.ConnectError:
            return {"status": "failed", "category": "connection_failed"}
        except httpx.RequestError as exc:
            return {"status": "failed", "category": exc.__class__.__name__}

    def _playwright_status(self) -> dict[str, Any]:
        try:
            module = importlib.import_module("playwright.async_api")
        except ImportError:
            return {"package": "missing", "chromium": "not_checked"}
        chromium = "needs_manual_check"
        try:
            package_path = Path(str(getattr(module, "__file__", ""))).resolve()
        except Exception:
            package_path = None
        return {
            "package": "available",
            "chromium": chromium,
            "package_path": str(package_path) if package_path else None,
        }

    def _secret_status(self, value: str | None) -> str:
        return "set" if str(value or "").strip() else "not_set"

    def _enabled(self, value: bool) -> str:
        return "enabled" if value else "disabled"


def log_startup_config(settings: Settings | None = None) -> None:
    try:
        service = ConfigDiagnosticService(settings or get_settings())
        snapshot = service.startup_snapshot()
        LOGGER.info("Analyse config loaded: %s", snapshot)
    except Exception as exc:
        LOGGER.warning("Không tạo được startup config snapshot: %s", exc.__class__.__name__)
