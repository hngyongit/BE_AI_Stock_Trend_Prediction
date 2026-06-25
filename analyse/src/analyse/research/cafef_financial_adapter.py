from __future__ import annotations

import asyncio
import hashlib
import html as html_lib
import importlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings, get_settings
from analyse.research.vietstock_financial_adapter import VietstockFinancialAdapter
from analyse.research.vietstock_financial_adapter import _TableParser
from analyse.research.vietstock_financial_adapter import _dedupe_preserve_order
from analyse.services.stock_data_service import StockDataService
from analyse.utils.asyncio_windows import ensure_windows_proactor_event_loop_policy
from analyse.utils.asyncio_windows import run_in_windows_proactor_thread
from analyse.utils.datetime_utils import now_iso
from analyse.utils.playwright_safe import PlaywrightTimeoutError
from analyse.utils.playwright_safe import TargetClosedError
from analyse.utils.playwright_safe import cancel_pending_tasks_safely
from analyse.utils.playwright_safe import cleanup_playwright_runtime_safely
from analyse.utils.playwright_safe import gather_safely
from analyse.utils.playwright_safe import infer_symbol_from_url
from analyse.utils.playwright_safe import is_playwright_timeout_error
from analyse.utils.playwright_safe import is_target_closed_error
from analyse.utils.playwright_safe import safe_playwright_error_message
from analyse.utils.debug_scrub import scrub_debug_payload, scrub_debug_text
from analyse.utils.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)

CAFEF_FINANCIAL_WAIT_UNTIL = "domcontentloaded"
CAFEF_FINANCIAL_TIMEOUT_WARNING = "CafeF financial page timed out before usable financial periods were extracted."
CAFEF_FINANCIAL_URL_TEMPLATE = "https://cafef.vn/du-lieu/{exchange}/{symbol}-tai-chinh.chn"


def build_cafef_financial_url(symbol: str, exchange: str | None = None, template: str | None = None) -> str:
    symbol_clean = str(symbol or "").strip().lower()
    exchange_clean = str(exchange or "HOSE").strip().lower() or "hose"
    url_template = template or CAFEF_FINANCIAL_URL_TEMPLATE
    url = url_template.format(exchange=exchange_clean, symbol=symbol_clean).strip()
    return re.sub(r"(?<!:)//+", "/", url)


class PlaywrightCafeFFinancialRenderer:
    """Render trang tài chính CafeF khi bảng được tải động."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_rendered_html(self, url: str) -> tuple[str | None, list[str]]:
        ensure_windows_proactor_event_loop_policy()
        return await run_in_windows_proactor_thread(lambda: self._fetch_rendered_html_direct(url))

    async def _fetch_rendered_html_direct(self, url: str) -> tuple[str | None, list[str]]:
        try:
            playwright_api = importlib.import_module("playwright.async_api")
        except ImportError:
            return None, ["Playwright chưa được cài đặt hoặc Chromium chưa sẵn sàng cho CafeF financial fallback."]

        async_playwright = playwright_api.async_playwright
        browser = None
        context = None
        page = None
        captured_payloads: list[str] = []
        pending_tasks: list[asyncio.Task[Any]] = []
        label = "playwright:cafef-financial"
        response_handler = None
        debug_error: BaseException | None = None
        debug_phase = "unknown"
        timeout_ms = self._navigation_timeout_ms()
        wait_until = CAFEF_FINANCIAL_WAIT_UNTIL
        try:
            async with async_playwright() as playwright:
                logger.info("[%s] launch browser", label)
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1600, "height": 1100},
                    user_agent=self.settings.research_user_agent,
                )
                page = await context.new_page()

                async def capture_response(response: Any) -> None:
                    try:
                        content_type = (response.headers or {}).get("content-type", "")
                        if "json" not in content_type.lower():
                            return
                        text = await response.text()
                        normalized = text.lower()
                        if any(marker in normalized for marker in ("doanh thu", "lợi nhuận", "loi nhuan", "profit", "totalassets", "quarter")):
                            captured_payloads.append(text[:500_000])
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        if is_target_closed_error(exc) or is_playwright_timeout_error(exc):
                            raise
                        logger.debug("[%s] response handler ignored: %s", label, exc)

                def on_response(response: Any) -> None:
                    task = asyncio.create_task(capture_response(response))
                    pending_tasks.append(task)

                response_handler = on_response
                page.on("response", response_handler)
                logger.info("[%s] goto URL", label)
                debug_phase = "page.goto"
                await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                debug_phase = "content_wait"
                await self._wait_for_content(page)
                debug_phase = "select_financial_tabs"
                await self._select_financial_tabs(page)
                debug_phase = "post_dom_wait"
                await page.wait_for_timeout(1500)
                if pending_tasks:
                    results = await gather_safely(pending_tasks, label=label)
                    for result in results:
                        if isinstance(result, BaseException) and debug_error is None:
                            debug_error = result
                            debug_phase = "response_handler"
                logger.info("[%s] extract table", label)
                html_text = await page.content()
                if captured_payloads:
                    html_text += "".join(
                        f'<script type="application/json" data-vietstock-financial-xhr>{html_lib.escape(payload)}</script>'
                        for payload in captured_payloads[:5]
                    )
                return html_text, []
        except asyncio.CancelledError as exc:
            debug_error = exc
            debug_phase = "cancelled"
            logger.warning("[%s] Request cancelled; cleaning up Playwright", label)
            await cancel_pending_tasks_safely(pending_tasks, label=label)
            raise
        except TargetClosedError as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            debug_phase = "goto/extract"
            message = safe_playwright_error_message(exc)
            logger.warning("[%s] Playwright target closed: %s", label, message)
            return None, [f"CafeF financial rendering failed: TargetClosedError: {message}"]
        except PlaywrightTimeoutError as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            logger.warning("[%s] timeout after %sms; continue with fallback source", label, timeout_ms)
            return None, [CAFEF_FINANCIAL_TIMEOUT_WARNING]
        except Exception as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            debug_phase = "goto/extract"
            if is_target_closed_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright target closed: %s", label, message)
                return None, [f"CafeF financial rendering failed: TargetClosedError: {message}"]
            if is_playwright_timeout_error(exc):
                debug_error = exc
                logger.warning("[%s] timeout after %sms; continue with fallback source", label, timeout_ms)
                return None, [CAFEF_FINANCIAL_TIMEOUT_WARNING]
            logger.warning("[%s] Playwright crawler failed safely: %s", label, exc, exc_info=True)
            return None, [f"CafeF financial rendering failed: {exc.__class__.__name__}: {self._safe_error_message(exc)}"]
        finally:
            if debug_error is not None and is_playwright_timeout_error(debug_error):
                self._save_timeout_debug(
                    url,
                    timeout_ms=timeout_ms,
                    wait_until=wait_until,
                    error=debug_error,
                    phase=debug_phase,
                )
            await cleanup_playwright_runtime_safely(
                page=page,
                context=context,
                browser=browser,
                pending_tasks=pending_tasks,
                response_handler=response_handler,
                label=label,
                debug_settings=self.settings,
                debug_source="CafeF tài chính",
                debug_url=url,
                debug_slug="cafef_financial",
                debug_error=debug_error,
                debug_phase=debug_phase,
            )

    async def _wait_for_content(self, page: Any) -> None:
        for selector in (
            "table",
            "text=Doanh thu thuần",
            "text=Thu nhập lãi thuần",
            "text=Lợi nhuận sau thuế",
            "text=Tổng cộng tài sản",
            "text=Lưu chuyển tiền",
            "text=Báo cáo tài chính",
            "[class*=financial]",
            "[id*=finance]",
        ):
            try:
                await page.wait_for_selector(selector, timeout=4000)
                return
            except Exception:
                continue

    async def _select_financial_tabs(self, page: Any) -> None:
        for text in (
            "Quý",
            "Tỷ đồng",
            "Kết quả kinh doanh",
            "Cân đối kế toán",
            "Lưu chuyển tiền tệ",
            "Chỉ số tài chính",
        ):
            for selector in (f"text={text}", f"a:has-text('{text}')", f"button:has-text('{text}')", f"label:has-text('{text}')"):
                try:
                    locator = page.locator(selector).first()
                    if await locator.count() <= 0:
                        continue
                    if await locator.is_visible(timeout=700):
                        await locator.click(timeout=1200)
                        await page.wait_for_timeout(300)
                        break
                except Exception:
                    continue

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        return (message[:177].rstrip() + "...") if len(message) > 180 else message or "không có thông điệp chi tiết"

    def _navigation_timeout_ms(self) -> int:
        try:
            timeout_ms = int(self.settings.cafef_financial_timeout_ms)
        except (TypeError, ValueError):
            return 90000
        return timeout_ms if timeout_ms > 0 else 90000

    def _save_timeout_debug(
        self,
        url: str,
        *,
        timeout_ms: int,
        wait_until: str,
        error: BaseException,
        phase: str,
    ) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        payload = {
            "source": "CafeF tài chính",
            "url": self._scrub_debug_payload(url),
            "timeout_ms": timeout_ms,
            "wait_until": wait_until,
            "error_type": "PlaywrightTimeoutError",
            "phase": phase,
            "fallback_used": True,
            "report_blocked": False,
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            symbol = infer_symbol_from_url(url)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_financial_timeout.json").write_text(
                json.dumps(self._scrub_debug_payload(payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _scrub_debug_payload(self, value: Any) -> Any:
        return scrub_debug_payload(value)


class CafeFFinancialAdapter:
    source_name = "CafeF tài chính"

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: HttpClient | None = None,
        browser_renderer: PlaywrightCafeFFinancialRenderer | Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client or HttpClient(timeout_ms=self.settings.cafef_financial_timeout_ms)
        self.browser_renderer = browser_renderer or PlaywrightCafeFFinancialRenderer(self.settings)
        self.cache_dir = Path(self.settings.research_cache_dir)
        self._parser = VietstockFinancialAdapter(self.settings, http_client=self.http_client)

    async def fetch(self, symbol: str, exchange: str | None = None) -> dict[str, Any]:
        clean_symbol = normalize_symbol(symbol)
        source_url = build_cafef_financial_url(
            clean_symbol,
            exchange or "HOSE",
            self.settings.cafef_financial_url_template,
        )
        if not self.settings.enable_cafef_financial_fallback:
            return self._result(source_url, [], ["CafeF tài chính fallback đang tắt theo cấu hình."], [], "disabled")

        warnings: list[str] = []
        technical_warnings: list[str] = []
        try:
            html_text = await self._fetch_with_retries(source_url, "static")
        except Exception as exc:
            html_text = ""
            warnings.append("Dữ liệu tài chính CafeF chưa sẵn sàng trong lần chạy này.")
            technical_warnings.append(f"CafeF financial static fetch failed: {exc.__class__.__name__}: {exc}")

        parsed = self.parse_html(html_text, source_url=source_url)
        if parsed.get("periods"):
            self._save_extraction_debug(clean_symbol, source_url, parsed, render_status="static_success", html_text=html_text)
            return parsed

        warnings.extend(self._as_list(parsed.get("warnings")))
        technical_warnings.extend(self._as_list(parsed.get("technical_warnings")))

        if self.settings.cafef_financial_use_browser_fallback:
            rendered_html = self._read_cache(source_url, "rendered")
            if rendered_html is None:
                rendered_html, browser_warnings = await self._fetch_rendered_with_retries(source_url)
                warnings.extend(browser_warnings)
                technical_warnings.extend(browser_warnings)
                if rendered_html:
                    self._write_cache(source_url, rendered_html, "rendered")
                    self._save_rendered_debug(clean_symbol, rendered_html)
            if rendered_html:
                rendered_parsed = self.parse_html(rendered_html, source_url=source_url)
                warnings.extend(self._as_list(rendered_parsed.get("warnings")))
                technical_warnings.extend(self._as_list(rendered_parsed.get("technical_warnings")))
                if rendered_parsed.get("periods"):
                    result = dict(rendered_parsed)
                    result["warnings"] = _dedupe_preserve_order(warnings)
                    result["technical_warnings"] = _dedupe_preserve_order(technical_warnings)
                    self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_success", html_text=rendered_html)
                    return result
        else:
            warnings.append("CafeF financial browser fallback đang tắt theo cấu hình.")

        result = self._result(
            source_url,
            [],
            _dedupe_preserve_order(warnings or ["Dữ liệu BCTC CafeF chưa đủ chỉ tiêu định lượng."]),
            _dedupe_preserve_order(technical_warnings),
            "insufficient",
        )
        self._save_extraction_debug(clean_symbol, source_url, result, render_status="insufficient", html_text=html_text)
        return result

    def parse_html(self, html_text: str, *, source_url: str) -> dict[str, Any]:
        parsed = self._parser.parse_html(html_text or "", source_url=source_url)
        raw_audit = self._extract_table_audit(html_text or "")
        periods = parsed.get("periods") if isinstance(parsed.get("periods"), list) else []
        valid_periods = StockDataService.valid_financial_periods(periods)
        unit = parsed.get("unit") or self.settings.cafef_financial_unit
        warnings = [
            self._friendly_warning(warning)
            for warning in self._as_list(parsed.get("warnings"))
        ]
        technical_warnings = self._as_list(parsed.get("technical_warnings"))
        full_periods = [period for period in valid_periods if self._is_full_bctc_period(period)]
        ratio_periods = [period for period in valid_periods if self._is_ratio_period(period)]
        if full_periods:
            usable_periods = valid_periods[: self.settings.cafef_financial_max_periods]
            status = "success"
            warnings = self._drop_period_only_warnings(warnings)
            ratio_only = False
        elif ratio_periods:
            usable_periods = ratio_periods[: self.settings.cafef_financial_max_periods]
            status = "partial"
            warnings = self._drop_period_only_warnings(warnings)
            warnings.append("CafeF hiện chỉ trích xuất được nhóm chỉ số tài chính; chưa đủ để xem là bộ BCTC đầy đủ.")
            ratio_only = True
        else:
            usable_periods = []
            status = "insufficient" if raw_audit.get("tables_found") or raw_audit.get("raw_period_headers") else "failed"
            ratio_only = False
            if periods:
                warnings.append("CafeF chỉ nhận diện được kỳ báo cáo nhưng chưa đủ chỉ tiêu định lượng.")
        result = self._result(
            source_url,
            usable_periods,
            _dedupe_preserve_order(warnings),
            _dedupe_preserve_order(technical_warnings),
            status,
            unit=unit,
            financial_ratios_only=ratio_only,
        )
        audit = self._build_audit(
            source_url=source_url,
            html_text=html_text or "",
            raw_audit=raw_audit,
            periods=usable_periods,
            status=status,
            warnings=result["warnings"],
        )
        result["audit"] = audit
        result["mapped_metrics"] = audit["mapped_metrics"]
        result["unmapped_metrics"] = audit["unmapped_metrics"]
        result["normalized_metrics_count"] = audit["normalized_metrics_count"]
        return result

    def _is_full_bctc_period(self, period: dict[str, Any]) -> bool:
        normal_keys = {
            "revenue",
            "gross_profit",
            "operating_profit",
            "profit_before_tax",
            "profit_after_tax",
            "parent_profit",
            "total_assets",
            "total_liabilities",
            "equity",
            "cash_and_equivalents",
            "inventory",
            "short_term_debt",
            "long_term_debt",
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
        }
        bank_keys = {
            "net_interest_income",
            "net_fee_income",
            "trading_income",
            "other_income",
            "operating_expenses",
            "pre_provision_operating_profit",
            "profit_before_tax",
            "profit_after_tax",
            "total_assets",
            "customer_loans",
            "customer_deposits",
            "equity",
            "nim",
            "npl_ratio",
            "casa_ratio",
            "cir",
        }
        normal_count = sum(1 for key in normal_keys if self._is_number(period.get(key)))
        bank_count = sum(1 for key in bank_keys if self._is_number(period.get(key)))
        return normal_count >= 3 or bank_count >= 3

    def _is_ratio_period(self, period: dict[str, Any]) -> bool:
        ratio_keys = {
            "eps",
            "eps_ttm",
            "bvps",
            "pe",
            "pb",
            "roe",
            "roa",
            "gross_margin",
            "net_margin",
            "current_ratio",
            "interest_coverage",
            "debt_ratio",
            "debt_to_assets",
            "debt_to_equity",
            "nim",
            "npl_ratio",
            "casa_ratio",
        }
        return sum(1 for key in ratio_keys if self._is_number(period.get(key))) >= 2

    def _is_number(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _drop_period_only_warnings(self, warnings: list[str]) -> list[str]:
        return [
            warning
            for warning in warnings
            if "chỉ nhận diện được kỳ" not in warning.lower()
            and "chưa trích xuất đủ số liệu" not in warning.lower()
        ]

    def _friendly_warning(self, warning: str) -> str:
        text = str(warning or "")
        text = text.replace("Vietstock Finance", "CafeF").replace("Vietstock", "CafeF")
        text = text.replace("HTML Vietstock Finance", "HTML CafeF")
        return text

    async def _fetch_with_cache(self, url: str, cache_kind: str) -> str:
        cached = self._read_cache(url, cache_kind)
        if cached is not None:
            return cached
        text = await self.http_client.get_text(url, headers={"User-Agent": self.settings.research_user_agent})
        self._write_cache(url, text, cache_kind)
        return text

    async def _fetch_with_retries(self, url: str, cache_kind: str) -> str:
        attempts = max(1, int(getattr(self.settings, "playwright_retry_count", 2) or 2))
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                return await self._fetch_with_cache(url, cache_kind)
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(max(0, int(getattr(self.settings, "playwright_retry_backoff_ms", 1500) or 0)) / 1000)
        assert last_exc is not None
        raise last_exc

    async def _fetch_rendered_with_retries(self, url: str) -> tuple[str | None, list[str]]:
        attempts = max(1, int(getattr(self.settings, "playwright_retry_count", 2) or 2))
        warnings: list[str] = []
        for attempt in range(attempts):
            html_text, attempt_warnings = await self.browser_renderer.fetch_rendered_html(url)
            warnings.extend(self._as_list(attempt_warnings))
            if html_text:
                return html_text, _dedupe_preserve_order(warnings)
            if attempt < attempts - 1:
                await asyncio.sleep(max(0, int(getattr(self.settings, "playwright_retry_backoff_ms", 1500) or 0)) / 1000)
        return None, _dedupe_preserve_order(warnings)

    def _cache_path(self, url: str, cache_kind: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"cafef_financial_{cache_kind}_{digest}.json"

    def _read_cache(self, url: str, cache_kind: str) -> str | None:
        path = self._cache_path(url, cache_kind)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("cached_at") or 0) > self.settings.cafef_financial_cache_ttl_seconds:
                return None
            return str(payload.get("text") or "")
        except Exception:
            return None

    def _write_cache(self, url: str, text: str, cache_kind: str) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(url, cache_kind).write_text(
                json.dumps({"cached_at": time.time(), "text": text}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_rendered_debug(self, symbol: str, html_text: str) -> None:
        if not (self.settings.external_data_debug_save_rendered_html or self.settings.vietstock_debug_save_rendered_html):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_financial_rendered.html").write_text(scrub_debug_text(html_text), encoding="utf-8")
        except Exception:
            return

    def _save_extraction_debug(self, symbol: str, source_url: str, result: dict[str, Any], *, render_status: str, html_text: str) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        periods = result.get("periods") if isinstance(result.get("periods"), list) else []
        audit = result.get("audit") if isinstance(result.get("audit"), dict) else self._build_audit(
            source_url=source_url,
            html_text=html_text or "",
            raw_audit=self._extract_table_audit(html_text or ""),
            periods=periods,
            status=str(result.get("status") or ""),
            warnings=result.get("warnings") or [],
        )
        payload = {
            "source_url": source_url,
            "parser_mode": render_status,
            "table_headers_found": self._table_headers(html_text),
            "row_count": len(re.findall(r"(?is)<tr\b", html_text or "")),
            "financial_audit": audit,
            "accepted_rows": periods,
            "final_normalized_data": result,
            "source_status": result.get("status"),
            "warnings": result.get("warnings") or [],
            "technical_warnings": result.get("technical_warnings") or [],
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_financial_extraction.json").write_text(
                json.dumps(self._scrub_debug_payload(payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_financial_audit.json").write_text(
                json.dumps(self._scrub_debug_payload({"symbol": normalize_symbol(symbol), **audit}), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _table_headers(self, html_text: str) -> list[str]:
        headers = []
        for match in re.finditer(r"(?is)<th[^>]*>(.*?)</th>", html_text or ""):
            clean = re.sub(r"<[^>]+>", " ", match.group(1))
            clean = re.sub(r"\s+", " ", html_lib.unescape(clean)).strip()
            if clean:
                headers.append(clean)
        return headers[:60]

    def _extract_table_audit(self, html_text: str) -> dict[str, Any]:
        parser = _TableParser()
        try:
            parser.feed(html_text or "")
        except Exception:
            return {
                "tables_found": 0,
                "raw_period_headers": [],
                "raw_metric_rows_count": 0,
                "mapped_metrics": [],
                "unmapped_metrics": [],
            }
        period_headers: list[str] = []
        mapped: dict[str, dict[str, str]] = {}
        unmapped: list[str] = []
        metric_rows = 0
        for table in parser.tables:
            table_period_indexes: set[int] = set()
            for row in table[:8]:
                for index, cell in enumerate(row):
                    meta = self._parser._parse_period(cell)  # noqa: SLF001 - shared parser contract
                    if meta:
                        period_headers.append(str(meta.get("period") or cell))
                        table_period_indexes.add(index)
            for row in table:
                if len(row) < 2:
                    continue
                if any(self._parser._parse_period(cell) for idx, cell in enumerate(row) if idx in table_period_indexes):  # noqa: SLF001
                    continue
                label = ""
                for index, cell in enumerate(row):
                    if index not in table_period_indexes and cell:
                        label = cell
                        break
                if not label:
                    continue
                values = [self._parser._parse_number(cell) for idx, cell in enumerate(row) if idx in table_period_indexes]  # noqa: SLF001
                if not any(value is not None for value in values):
                    continue
                metric_rows += 1
                field = self._parser._map_label_to_field(label)  # noqa: SLF001
                if field:
                    mapped[field] = {"field": field, "raw_label": label}
                elif label not in unmapped:
                    unmapped.append(label)
        return {
            "tables_found": len(parser.tables),
            "raw_period_headers": _dedupe_preserve_order(period_headers)[:40],
            "raw_metric_rows_count": metric_rows,
            "mapped_metrics": list(mapped.values()),
            "unmapped_metrics": unmapped[:80],
        }

    def _build_audit(
        self,
        *,
        source_url: str,
        html_text: str,
        raw_audit: dict[str, Any],
        periods: list[dict[str, Any]],
        status: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        mapped_metric_names = self._financial_metrics_found(periods)
        return {
            "url": source_url,
            "attempted": True,
            "page_loaded": bool(html_text),
            "tables_found": raw_audit.get("tables_found") or 0,
            "raw_period_headers": raw_audit.get("raw_period_headers") or [],
            "raw_metric_rows_count": raw_audit.get("raw_metric_rows_count") or 0,
            "normalized_periods_count": len(periods),
            "normalized_metrics_count": sum(
                1
                for period in periods
                if isinstance(period, dict)
                for key, value in period.items()
                if key not in {"period", "year", "quarter"} and isinstance(value, (int, float)) and not isinstance(value, bool)
            ),
            "mapped_metrics": raw_audit.get("mapped_metrics") or [{"field": field, "raw_label": field} for field in mapped_metric_names],
            "unmapped_metrics": raw_audit.get("unmapped_metrics") or [],
            "merge_contributions": [],
            "source_status_before": status,
            "source_status_after": status,
            "warnings": warnings,
        }

    def _financial_metrics_found(self, periods: list[dict[str, Any]]) -> list[str]:
        metrics: set[str] = set()
        for period in periods:
            if not isinstance(period, dict):
                continue
            for key, value in period.items():
                if key in {"period", "year", "quarter", "source", "source_url"}:
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    metrics.add(key)
        return sorted(metrics)

    def _scrub_debug_payload(self, value: Any) -> Any:
        return scrub_debug_payload(value)

    def _result(
        self,
        source_url: str,
        periods: list[dict[str, Any]],
        warnings: list[str],
        technical_warnings: list[str],
        status: str,
        unit: str | None = None,
        financial_ratios_only: bool = False,
    ) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "source_url": source_url,
            "fetched_at": now_iso(),
            "unit": unit or self.settings.cafef_financial_unit,
            "periods": periods,
            "financial_ratios_only": financial_ratios_only,
            "warnings": _dedupe_preserve_order(warnings),
            "technical_warnings": _dedupe_preserve_order(technical_warnings),
            "status": status,
        }

    def _as_list(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return [str(value)]
