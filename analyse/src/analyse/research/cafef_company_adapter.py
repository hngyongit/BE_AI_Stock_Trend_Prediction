from __future__ import annotations

import asyncio
import hashlib
import html as html_lib
import importlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings, get_settings
from analyse.research.vietstock_financial_adapter import _TableParser, _dedupe_preserve_order
from analyse.utils.asyncio_windows import ensure_windows_proactor_event_loop_policy
from analyse.utils.asyncio_windows import run_in_windows_proactor_thread
from analyse.utils.datetime_utils import now_iso
from analyse.utils.playwright_safe import PlaywrightTimeoutError
from analyse.utils.playwright_safe import TargetClosedError
from analyse.utils.playwright_safe import cancel_pending_tasks_safely
from analyse.utils.playwright_safe import cleanup_playwright_runtime_safely
from analyse.utils.playwright_safe import gather_safely
from analyse.utils.playwright_safe import is_playwright_timeout_error
from analyse.utils.playwright_safe import is_target_closed_error
from analyse.utils.playwright_safe import safe_playwright_error_message
from analyse.utils.debug_scrub import scrub_debug_payload, scrub_debug_text
from analyse.utils.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


_COMPANY_NAVIGATION_TERMS = (
    "Bảng giá điện tử",
    "Danh mục đầu tư",
    "Thoát",
    "Đổi mật khẩu",
    "MỚI NHẤT",
    "Đọc nhanh",
    "XÃ HỘI",
    "CHỨNG KHOÁN",
    "BẤT ĐỘNG SẢN",
    "DOANH NGHIỆP",
    "CafeF",
    "Đăng nhập",
)


def build_cafef_company_url(symbol: str, exchange: str, template: str | None = None) -> str:
    symbol_clean = str(symbol or "").strip().lower()
    exchange_clean = str(exchange or "").strip().lower() or "hose"
    url_template = template or "https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn"
    url = url_template.format(exchange=exchange_clean, symbol=symbol_clean).strip()
    return re.sub(r"(?<!:)//+", "/", url)


def clean_company_name(raw: str, symbol: str) -> str | None:
    """Làm sạch tên doanh nghiệp lấy từ CafeF, tránh dính menu/header."""
    text = re.sub(r"\s+", " ", html_lib.unescape(str(raw or ""))).strip(" -–|:")
    if not text:
        return None
    text = re.sub(r"(?i)^ban lãnh đạo\s*&?\s*sở hữu\s*[-–:|]\s*", "", text).strip()
    text = re.sub(rf"(?i)^\s*{re.escape(symbol)}\s*[-–:|]\s*", "", text).strip()
    for term in _COMPANY_NAVIGATION_TERMS:
        index = text.lower().find(term.lower())
        if index > 0:
            text = text[:index].strip(" -–|:")
    match = re.search(
        r"((?:CTCP|Công ty|Ngân hàng|Tổng công ty|Tập đoàn)[^|]{4,180})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        text = match.group(1).strip(" -–|:")
        for term in _COMPANY_NAVIGATION_TERMS:
            index = text.lower().find(term.lower())
            if index > 0:
                text = text[:index].strip(" -–|:")
    normalized = _normalize_for_company_check(text)
    forbidden = [_normalize_for_company_check(term) for term in _COMPANY_NAVIGATION_TERMS]
    if any(term in normalized for term in forbidden):
        return None
    if len(text) < 4 or len(text) > 180:
        return None
    if not re.search(r"(?i)\b(CTCP|Công ty|Ngân hàng|Tổng công ty|Tập đoàn|TMCP)\b", text):
        return None
    return text


def _normalize_for_company_check(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = normalized.lower().replace("đ", "d")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


class PlaywrightCafeFCompanyRenderer:
    """Render trang CafeF khi HTML tĩnh chưa có đủ thông tin doanh nghiệp."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_rendered_html(self, url: str) -> tuple[str | None, list[str]]:
        ensure_windows_proactor_event_loop_policy()
        return await run_in_windows_proactor_thread(lambda: self._fetch_rendered_html_direct(url))

    async def _fetch_rendered_html_direct(self, url: str) -> tuple[str | None, list[str]]:
        try:
            playwright_api = importlib.import_module("playwright.async_api")
        except ImportError:
            return None, ["Playwright chưa được cài đặt hoặc Chromium chưa sẵn sàng cho CafeF company fallback."]

        async_playwright = playwright_api.async_playwright
        captured_payloads: list[dict[str, str]] = []
        pending_tasks: list[asyncio.Task[Any]] = []
        browser = None
        context = None
        page = None
        label = "playwright:cafef-company"
        response_handler = None
        debug_error: BaseException | None = None
        debug_phase = "unknown"
        try:
            async with async_playwright() as playwright:
                logger.info("[%s] launch browser", label)
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    user_agent=self.settings.research_user_agent,
                )
                page = await context.new_page()

                async def capture_response(response: Any) -> None:
                    try:
                        response_url = str(response.url or "")
                        if "/du-lieu/Ajax/PageNew/" not in response_url:
                            return
                        text = await response.text()
                        captured_payloads.append({"url": response_url, "text": text[:500_000]})
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
                await page.goto(url, wait_until="domcontentloaded", timeout=max(self.settings.cafef_company_timeout_ms, 30000))
                await self._wait_for_content(page)
                await self._scroll_for_dynamic_content(page)
                if pending_tasks:
                    results = await gather_safely(pending_tasks, label=label)
                    for result in results:
                        if isinstance(result, BaseException) and debug_error is None:
                            debug_error = result
                            debug_phase = "response_handler"
                logger.info("[%s] extract table", label)
                html_text = await page.content()
                dom_payload = await self._extract_dom_payload(page)
                if captured_payloads:
                    html_text += "".join(
                        '<script type="application/json" data-cafef-company-xhr data-url="'
                        + html_lib.escape(item.get("url") or "")
                        + '">'
                        + html_lib.escape(item.get("text") or "")
                        + "</script>"
                        for item in captured_payloads[:8]
                    )
                if dom_payload:
                    html_text += (
                        '<script type="application/json" data-cafef-company-dom>'
                        + html_lib.escape(json.dumps(dom_payload, ensure_ascii=False))
                        + "</script>"
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
            return None, [f"CafeF company rendering failed: TargetClosedError: {message}"]
        except PlaywrightTimeoutError as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            debug_phase = "goto/extract"
            message = safe_playwright_error_message(exc)
            logger.warning("[%s] Playwright timeout: %s", label, message)
            return None, [f"CafeF company rendering failed: TimeoutError: {message}"]
        except Exception as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            debug_phase = "goto/extract"
            if is_target_closed_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright target closed: %s", label, message)
                return None, [f"CafeF company rendering failed: TargetClosedError: {message}"]
            if is_playwright_timeout_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright timeout: %s", label, message)
                return None, [f"CafeF company rendering failed: TimeoutError: {message}"]
            logger.warning("[%s] Playwright crawler failed safely: %s", label, exc, exc_info=True)
            return None, [f"CafeF company rendering failed: {exc.__class__.__name__}: {self._safe_error_message(exc)}"]
        finally:
            await cleanup_playwright_runtime_safely(
                page=page,
                context=context,
                browser=browser,
                pending_tasks=pending_tasks,
                response_handler=response_handler,
                label=label,
                debug_settings=self.settings,
                debug_source="CafeF thông tin doanh nghiệp",
                debug_url=url,
                debug_slug="cafef_company",
                debug_error=debug_error,
                debug_phase=debug_phase,
            )

    async def _wait_for_content(self, page: Any) -> None:
        for selector in ("table", "text=Ban lãnh đạo", "text=Hồ sơ công ty", "text=Ngành nghề", "text=Sở hữu"):
            try:
                await page.wait_for_selector(selector, timeout=3000)
                return
            except Exception:
                continue
        try:
            await page.wait_for_timeout(max(500, min(self.settings.playwright_extra_wait_ms, 3000)))
        except Exception:
            return

    async def _scroll_for_dynamic_content(self, page: Any) -> None:
        try:
            for y in (700, 1400, 2400, 3600, 5200, 7000):
                await page.evaluate(f"window.scrollTo(0,{y})")
                await page.wait_for_timeout(300)
            await page.evaluate("window.scrollTo(0,0)")
        except Exception:
            return

    async def _extract_dom_payload(self, page: Any) -> dict[str, Any] | None:
        try:
            return await page.evaluate(
                """() => {
                    const textOf = el => (el && (el.innerText || el.textContent) || '').replace(/\\s+/g, ' ').trim();
                    const tables = Array.from(document.querySelectorAll('table')).map((table, index) => ({
                        index,
                        headers: Array.from(table.querySelectorAll('thead th, tr:first-child th, tr:first-child td')).map(textOf),
                        rows: Array.from(table.querySelectorAll('tbody tr, tr')).slice(0, 120).map(row =>
                            Array.from(row.querySelectorAll('td, th')).map(textOf)
                        ),
                        text: textOf(table).slice(0, 2000)
                    }));
                    const markers = /Ban lãnh đạo|Lãnh đạo|Hội đồng quản trị|Ban giám đốc|Ban kiểm soát|Sở hữu|Cổ đông/i;
                    const sections = Array.from(document.querySelectorAll('section, article, div, ul, ol')).map((el, index) => ({
                        index,
                        tag: el.tagName,
                        id: el.id || '',
                        className: String(el.className || ''),
                        text: textOf(el).slice(0, 2400)
                    })).filter(item => markers.test(item.text)).slice(0, 80);
                    return {title: document.title, tables, sections};
                }"""
            )
        except Exception:
            return None

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        return (message[:177].rstrip() + "...") if len(message) > 180 else message or "không có thông điệp chi tiết"


class CafeFCompanyAdapter:
    source_name = "CafeF thông tin doanh nghiệp"

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: HttpClient | None = None,
        browser_renderer: PlaywrightCafeFCompanyRenderer | Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client or HttpClient(timeout_ms=self.settings.cafef_company_timeout_ms)
        self.browser_renderer = browser_renderer or PlaywrightCafeFCompanyRenderer(self.settings)
        self.cache_dir = Path(self.settings.research_cache_dir)

    async def fetch(self, symbol: str, exchange: str | None = None) -> dict[str, Any]:
        clean_symbol = normalize_symbol(symbol)
        clean_exchange = (exchange or "HOSE").strip() or "HOSE"
        source_url = build_cafef_company_url(
            clean_symbol,
            clean_exchange,
            self.settings.cafef_company_url_template,
        )
        if not self.settings.enable_cafef_company_fallback:
            result = self._result(
                source_url=source_url,
                symbol=clean_symbol,
                exchange=clean_exchange.upper(),
                status="disabled",
                warnings=["CafeF company fallback đang tắt theo cấu hình."],
            )
            self._save_url_debug(clean_symbol, source_url, result, http_status="disabled", parser_mode="disabled")
            return result

        warnings: list[str] = []
        technical_warnings: list[str] = []
        http_status = "loaded"
        try:
            html_text = await self._fetch_with_cache(source_url, "static")
            self._save_raw_debug(clean_symbol, html_text)
        except Exception as exc:
            html_text = ""
            http_status = "failed"
            warnings.append("Thông tin doanh nghiệp từ CafeF chưa sẵn sàng trong lần chạy này.")
            technical_warnings.append(f"CafeF company static fetch failed: {exc.__class__.__name__}: {exc}")

        parsed = self.parse_html(html_text, source_url=source_url, symbol=clean_symbol, exchange=clean_exchange.upper())
        ajax_payloads = []
        if http_status != "failed":
            try:
                ajax_payloads = await self._fetch_ajax_payloads(clean_symbol, source_url)
                parsed = self._merge_ajax_payloads(
                    parsed,
                    ajax_payloads,
                    source_url=source_url,
                    symbol=clean_symbol,
                    exchange=clean_exchange.upper(),
                )
            except Exception as exc:
                technical_warnings.append(f"CafeF company ajax extraction failed: {exc.__class__.__name__}: {exc}")
        parsed_has_useful_data = self._has_useful_company_data(parsed)
        best_partial = parsed if parsed_has_useful_data else None
        if parsed_has_useful_data and (
            parsed.get("status") == "success" or not self.settings.cafef_company_use_browser_fallback
        ):
            parsed["warnings"] = _dedupe_preserve_order(self._merge_string_lists(self._as_list(parsed.get("warnings")), warnings))
            parsed["technical_warnings"] = _dedupe_preserve_order(
                self._merge_string_lists(self._as_list(parsed.get("technical_warnings")), technical_warnings)
            )
            self._save_extraction_debug(clean_symbol, source_url, parsed, render_status="raw_html", html_text=html_text)
            self._save_url_debug(clean_symbol, source_url, parsed, http_status=http_status, parser_mode="raw_html")
            return parsed

        warnings.extend(self._as_list(parsed.get("warnings")))
        technical_warnings.extend(self._as_list(parsed.get("technical_warnings")))

        rendered_attempted = False
        if self.settings.cafef_company_use_browser_fallback:
            rendered_html = self._read_cache(source_url, "rendered")
            if rendered_html is None:
                rendered_attempted = True
                rendered_html, browser_warnings = await self.browser_renderer.fetch_rendered_html(source_url)
                warnings.extend(browser_warnings)
                technical_warnings.extend(browser_warnings)
                if rendered_html:
                    self._write_cache(source_url, rendered_html, "rendered")
                    self._save_rendered_debug(clean_symbol, rendered_html)
            if rendered_html:
                rendered_parsed = self.parse_html(rendered_html, source_url=source_url, symbol=clean_symbol, exchange=clean_exchange.upper())
                warnings.extend(self._as_list(rendered_parsed.get("warnings")))
                technical_warnings.extend(self._as_list(rendered_parsed.get("technical_warnings")))
                if self._has_useful_company_data(rendered_parsed):
                    rendered_parsed["warnings"] = _dedupe_preserve_order(warnings)
                    rendered_parsed["technical_warnings"] = _dedupe_preserve_order(technical_warnings)
                    rendered_parsed["status"] = self._status_for_fields(rendered_parsed)
                    self._save_extraction_debug(clean_symbol, source_url, rendered_parsed, render_status="playwright", html_text=rendered_html)
                    self._save_url_debug(
                        clean_symbol,
                        source_url,
                        rendered_parsed,
                        http_status=http_status,
                        parser_mode="playwright",
                        render_status="rendered" if rendered_attempted else "rendered_cache",
                    )
                    return rendered_parsed
        else:
            warnings.append("CafeF company browser fallback đang tắt theo cấu hình.")

        if best_partial:
            best_partial["warnings"] = _dedupe_preserve_order(warnings or self._as_list(best_partial.get("warnings")))
            best_partial["technical_warnings"] = _dedupe_preserve_order(technical_warnings or self._as_list(best_partial.get("technical_warnings")))
            best_partial["status"] = "partial"
            self._save_extraction_debug(clean_symbol, source_url, best_partial, render_status="raw_html_partial", html_text=html_text)
            self._save_url_debug(
                clean_symbol,
                source_url,
                best_partial,
                http_status=http_status,
                parser_mode="raw_html",
                render_status="partial_after_browser_fallback",
            )
            return best_partial

        result = self._result(
            source_url=source_url,
            symbol=clean_symbol,
            exchange=clean_exchange.upper(),
            status="insufficient" if http_status != "failed" else "failed",
            warnings=_dedupe_preserve_order(warnings or ["Thông tin mô tả doanh nghiệp từ CafeF chưa đủ để sử dụng."]),
            technical_warnings=_dedupe_preserve_order(technical_warnings),
            rejected_fields=["company_name", "leadership", "ownership"],
            rejection_reasons=["CafeF page loaded nhưng chưa tìm thấy profile/ban lãnh đạo/sở hữu đủ sạch."],
        )
        self._save_extraction_debug(clean_symbol, source_url, result, render_status="partial", html_text=html_text)
        self._save_url_debug(clean_symbol, source_url, result, http_status=http_status, parser_mode="raw_html", render_status="not_enough_data")
        return result

    def parse_html(self, html_text: str, *, source_url: str, symbol: str, exchange: str) -> dict[str, Any]:
        parser = _TableParser()
        parser.feed(html_text or "")
        text = self._clean_html_text(html_text)
        rows = [row for table in parser.tables for row in table]

        company_name = self._extract_company_name(rows, text, symbol)
        if not company_name:
            company_name = self._extract_company_name_from_metadata(html_text or "", symbol)
        industry_levels = self._extract_industry_levels(rows, text)
        sector = industry_levels.get("industry_level_1")
        industry_group = industry_levels.get("industry_level_2")
        industry_detail = industry_levels.get("industry_level_3")
        industry = industry_detail or industry_group
        business_overview = self._extract_labeled_value(
            rows,
            text,
            ("nganh nghe kinh doanh", "hoat dong kinh doanh", "linh vuc kinh doanh", "gioi thieu", "mo ta"),
            min_length=24,
        )
        leadership = self._extract_people_table(parser.tables, table_kind="leadership")
        ownership = self._extract_people_table(parser.tables, table_kind="ownership")

        accepted_fields = self._accepted_company_fields(
            company_name=company_name,
            industry_level_1=sector,
            industry_level_2=industry_group,
            industry_level_3=industry_detail,
            business_overview=business_overview,
            leadership=leadership,
            ownership=ownership,
        )
        rejected_fields = []
        rejection_reasons = []
        if not company_name:
            rejected_fields.append("company_name")
            rejection_reasons.append("Không tìm thấy tên doanh nghiệp sạch trong vùng nội dung CafeF.")
        if not any([sector, industry_group, industry_detail]):
            rejected_fields.append("industry_levels")
            rejection_reasons.append("CafeF chưa cung cấp đủ phân cấp ngành trong HTML đã đọc.")
        if not business_overview:
            rejected_fields.append("business_overview")
            rejection_reasons.append("CafeF chưa cung cấp mô tả hoạt động kinh doanh đủ dài.")

        status = self._status_for_fields(
            {
                "company_name": company_name,
                "industry_level_1": sector,
                "industry_level_2": industry_group,
                "industry_level_3": industry_detail,
                "business_overview": business_overview,
                "leadership": leadership,
                "ownership": ownership,
            }
        )
        warnings = []
        if not accepted_fields:
            warnings.append("Thông tin mô tả doanh nghiệp từ CafeF chưa đủ để sử dụng.")
        elif status == "partial":
            warnings.append("CafeF mới ghi nhận được một phần thông tin doanh nghiệp; các trường thiếu sẽ giữ từ nguồn sạch khác nếu có.")

        base_result = self._result(
            source_url=source_url,
            symbol=symbol,
            exchange=exchange,
            company_name=company_name,
            industry=industry,
            sector=sector,
            industry_level_1=sector,
            industry_level_2=industry_group,
            industry_level_3=industry_detail,
            business_overview=business_overview,
            leadership=leadership,
            ownership=ownership,
            status=status,
            warnings=warnings,
            technical_warnings=[],
            accepted_fields=accepted_fields,
            rejected_fields=rejected_fields,
            rejection_reasons=rejection_reasons,
            selectors_found=self._selectors_found(html_text or ""),
        )
        embedded_payloads = self._embedded_ajax_payloads(html_text or "")
        if embedded_payloads:
            return self._merge_ajax_payloads(
                base_result,
                embedded_payloads,
                source_url=source_url,
                symbol=symbol,
                exchange=exchange,
            )
        return base_result

    def _embedded_ajax_payloads(self, html_text: str) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for match in re.finditer(
            r'<script[^>]*data-cafef-company-xhr[^>]*data-url=["\']([^"\']*)["\'][^>]*>(.*?)</script>',
            html_text or "",
            flags=re.IGNORECASE | re.DOTALL,
        ):
            url = html_lib.unescape(match.group(1) or "")
            raw = html_lib.unescape(match.group(2) or "")
            kind = "company_intro"
            lower_url = url.lower()
            if "listceo" in lower_url:
                kind = "leadership"
            elif "cocausohuu" in lower_url and "type=sohuu" in lower_url:
                kind = "company_holdings"
            elif "cocausohuu" in lower_url:
                kind = "ownership"
            try:
                payload = json.loads(raw)
            except Exception:
                payloads.append({"kind": kind, "url": url, "status": "failed", "error": "embedded_json_parse_failed"})
                continue
            payloads.append({"kind": kind, "url": url, "status": "success", "raw_length": len(raw), "payload": payload})
        return payloads

    async def _fetch_ajax_payloads(self, symbol: str, source_url: str) -> list[dict[str, Any]]:
        symbol_lower = normalize_symbol(symbol).lower()
        endpoints = [
            ("company_intro", f"https://cafef.vn/du-lieu/Ajax/PageNew/CompanyIntro.ashx?Symbol={symbol_lower}"),
            ("leadership", f"https://cafef.vn/du-lieu/Ajax/PageNew/ListCeo.ashx?Symbol={symbol_lower}&PositionGroup=0"),
            ("ownership", f"https://cafef.vn/du-lieu/Ajax/PageNew/CoCauSoHuu.ashx?Symbol={symbol_lower}"),
            ("company_holdings", f"https://cafef.vn/du-lieu/Ajax/PageNew/CoCauSoHuu.ashx?Symbol={symbol_lower}&Type=SoHuu"),
        ]
        payloads: list[dict[str, Any]] = []
        for kind, url in endpoints:
            item: dict[str, Any] = {"kind": kind, "url": url, "status": "failed"}
            try:
                text = await self.http_client.get_text(
                    url,
                    headers={"User-Agent": self.settings.research_user_agent, "Referer": source_url},
                )
                item["raw_length"] = len(text or "")
                item["payload"] = json.loads(text or "{}")
                item["status"] = "success"
            except Exception as exc:
                item["error"] = f"{exc.__class__.__name__}: {exc}"
            payloads.append(item)
        return payloads

    def _merge_ajax_payloads(
        self,
        result: dict[str, Any],
        ajax_payloads: list[dict[str, Any]],
        *,
        source_url: str,
        symbol: str,
        exchange: str,
    ) -> dict[str, Any]:
        if not ajax_payloads:
            return result
        merged = dict(result)
        accepted_rows: list[dict[str, Any]] = list(self._as_list_dicts((merged.get("debug") or {}).get("accepted_rows")))
        rejected_rows: list[dict[str, Any]] = list(self._as_list_dicts((merged.get("debug") or {}).get("rejected_rows")))
        company_name = merged.get("company_name")
        business_overview = merged.get("business_overview")
        leadership = list(self._as_list_dicts(merged.get("leadership")))
        ownership = list(self._as_list_dicts(merged.get("ownership")))
        company_holdings: list[dict[str, Any]] = []

        for item in ajax_payloads:
            payload = item.get("payload")
            if not isinstance(payload, dict):
                rejected_rows.append({"raw": item.get("url"), "reason": item.get("error") or "ajax_payload_invalid"})
                continue
            kind = str(item.get("kind") or "")
            data = payload.get("Data")
            if kind == "company_intro" and isinstance(data, dict):
                ajax_name = clean_company_name(str(data.get("Name") or ""), symbol)
                if ajax_name:
                    company_name = company_name or ajax_name
                    accepted_rows.append({"source": "CompanyIntro", "field": "company_name", "value": ajax_name})
                intro = re.sub(r"\s+", " ", html_lib.unescape(str(data.get("Intro") or ""))).strip()
                if intro and len(intro) >= 24:
                    business_overview = business_overview or intro[:600]
                    accepted_rows.append({"source": "CompanyIntro", "field": "business_overview"})
                center_id = data.get("CenterId")
                if center_id and not merged.get("exchange"):
                    merged["exchange"] = self._exchange_from_center_id(center_id) or exchange
            elif kind == "leadership":
                rows, rejected = self._extract_leadership_from_ajax(payload)
                leadership.extend(rows)
                accepted_rows.extend({"source": "ListCeo", "field": "leadership", "raw": row.get("name")} for row in rows)
                rejected_rows.extend(rejected)
            elif kind == "ownership":
                rows, rejected = self._extract_ownership_from_ajax(payload)
                ownership.extend(rows)
                accepted_rows.extend({"source": "CoCauSoHuu", "field": "ownership", "raw": row.get("holder")} for row in rows)
                rejected_rows.extend(rejected)
            elif kind == "company_holdings":
                company_holdings = self._extract_company_holdings_from_ajax(payload)

        leadership = self._dedupe_people(leadership, identity_keys=("name", "position"))[:30]
        ownership = self._dedupe_people(ownership, identity_keys=("holder", "shares", "ownership_percent"))
        ownership = sorted(ownership, key=lambda row: self._ownership_rate_value(row.get("ownership_percent")), reverse=True)[:30]
        if company_holdings:
            merged["company_holdings"] = company_holdings[:20]

        accepted_fields = self._accepted_company_fields(
            company_name=company_name,
            industry_level_1=merged.get("industry_level_1") or merged.get("sector"),
            industry_level_2=merged.get("industry_level_2"),
            industry_level_3=merged.get("industry_level_3"),
            business_overview=business_overview,
            leadership=leadership,
            ownership=ownership,
        )
        rejected_fields = []
        rejection_reasons = []
        if not company_name:
            rejected_fields.append("company_name")
            rejection_reasons.append("Không tìm thấy tên doanh nghiệp sạch trong CafeF HTML/Ajax.")
        if not leadership:
            rejected_fields.append("leadership")
            rejection_reasons.append("Không tìm thấy dòng ban lãnh đạo hợp lệ từ ListCeo/Ajax hoặc DOM.")
        if not ownership:
            rejected_fields.append("ownership")
            rejection_reasons.append("Không tìm thấy dòng sở hữu/cổ đông hợp lệ từ CoCauSoHuu/Ajax hoặc DOM.")
        if not any([merged.get("industry_level_1") or merged.get("sector"), merged.get("industry_level_2"), merged.get("industry_level_3")]):
            rejected_fields.append("industry_levels")
            rejection_reasons.append("CafeF company page chưa cung cấp phân cấp ngành đủ sạch.")

        merged.update(
            {
                "company_name": company_name,
                "business_overview": business_overview,
                "leadership": leadership,
                "ownership": ownership,
                "accepted_fields": accepted_fields,
                "rejected_fields": rejected_fields,
                "rejection_reasons": rejection_reasons,
                "status": self._status_for_fields(
                    {
                        **merged,
                        "company_name": company_name,
                        "business_overview": business_overview,
                        "leadership": leadership,
                        "ownership": ownership,
                    }
                ),
                "confidence": self._confidence(
                    company_name=company_name,
                    industry_level_1=merged.get("industry_level_1") or merged.get("sector"),
                    industry_level_2=merged.get("industry_level_2"),
                    industry_level_3=merged.get("industry_level_3"),
                    business_overview=business_overview,
                    leadership=leadership,
                    ownership=ownership,
                ),
            }
        )
        if merged["status"] == "partial":
            merged["warnings"] = _dedupe_preserve_order(
                self._as_list(merged.get("warnings"))
                + ["CafeF mới ghi nhận được một phần thông tin doanh nghiệp; các trường thiếu sẽ giữ từ nguồn sạch khác nếu có."]
            )
        merged["debug"] = {
            **self._dict(merged.get("debug")),
            "ajax_payloads": [
                {
                    "kind": item.get("kind"),
                    "url": item.get("url"),
                    "status": item.get("status"),
                    "raw_length": item.get("raw_length"),
                    "error": item.get("error"),
                }
                for item in ajax_payloads
            ],
            "accepted_rows": accepted_rows[:200],
            "rejected_rows": rejected_rows[:200],
            "leadership_rows_found": len(leadership),
            "ownership_rows_found": len(ownership),
            "failure_reason": self._company_failure_reason(leadership, ownership, company_name),
        }
        return merged

    def _extract_leadership_from_ajax(self, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        rows: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []
        groups = payload.get("Data")
        if not isinstance(groups, list):
            return rows, [{"raw": "ListCeo", "reason": "payload.Data is not a list"}]
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_name = re.sub(r"\s+", " ", str(group.get("GroupName") or "")).strip()
            values = group.get("values")
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                name = self._clean_person_or_holder(item.get("Name"))
                position = re.sub(r"\s+", " ", str(item.get("Position") or "")).strip()
                if not name or not position:
                    rejected.append({"raw": json.dumps(item, ensure_ascii=False)[:400], "reason": "missing_name_or_position"})
                    continue
                row = {
                    "name": name,
                    "position": position,
                    "title": position,
                    "group": group_name or None,
                    "source": self.source_name,
                }
                if item.get("LinkCeoDetail"):
                    row["source_url"] = "https://cafef.vn" + str(item.get("LinkCeoDetail"))
                rows.append({key: value for key, value in row.items() if value not in (None, "", [], {})})
        return rows, rejected

    def _extract_ownership_from_ajax(self, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        rows: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []
        data = payload.get("Data")
        if isinstance(data, dict):
            values = data.get("CoDongSoHuu")
        else:
            values = data
        if not isinstance(values, list):
            return rows, [{"raw": "CoCauSoHuu", "reason": "payload.Data.CoDongSoHuu is not a list"}]
        for item in values:
            if not isinstance(item, dict):
                continue
            holder = self._clean_person_or_holder(item.get("Name") or self._clean_html_text(str(item.get("Url") or "")))
            shares = re.sub(r"\s+", " ", str(item.get("AssetVolume") or "")).strip()
            ratio = self._normalize_ownership_percent(item.get("AssetRate"))
            if not holder or (not shares and not ratio):
                rejected.append({"raw": json.dumps(item, ensure_ascii=False)[:400], "reason": "missing_holder_or_ownership_metric"})
                continue
            row = {
                "holder": holder,
                "name": holder,
                "shares": shares or None,
                "ownership_percent": ratio,
                "ratio": ratio,
                "updated_date": item.get("UpdatedDate"),
                "source": self.source_name,
            }
            rows.append({key: value for key, value in row.items() if value not in (None, "", [], {})})
        return rows, rejected

    def _extract_company_holdings_from_ajax(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("Data")
        if not isinstance(data, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = self._clean_person_or_holder(item.get("Name"))
            if not name:
                continue
            rows.append(
                {
                    "symbol": normalize_symbol(item.get("Code") or ""),
                    "company": name,
                    "shares": str(item.get("AssetVolume") or "").strip() or None,
                    "ownership_percent": self._normalize_ownership_percent(item.get("AssetRate")),
                    "updated_date": item.get("UpdatedDate"),
                    "source": self.source_name,
                }
            )
        return [{key: value for key, value in row.items() if value not in (None, "", [], {})} for row in rows]

    def _extract_industry_levels(self, rows: list[list[str]], text: str) -> dict[str, str]:
        levels: dict[str, str] = {}
        label_map = (
            ("industry_level_1", ("linh vuc", "nganh cap cao", "nganh cap 1", "sector")),
            ("industry_level_2", ("nhom nganh", "nganh cap 2", "sub sector", "industry group")),
            ("industry_level_3", ("nganh chi tiet", "nganh cap 3", "nganh")),
        )
        excluded_labels = ("nganh nghe kinh doanh", "linh vuc kinh doanh", "hoat dong kinh doanh")
        for row in rows:
            if len(row) < 2:
                continue
            left = self._normalize_text(row[0])
            if any(excluded in left for excluded in excluded_labels):
                continue
            value = " ".join(cell for cell in row[1:] if cell).strip()
            if not self._looks_like_industry_value(value):
                continue
            for target, labels in label_map:
                if any(label == left or label in left for label in labels):
                    levels.setdefault(target, value[:160])
                    break

        if not levels:
            levels.update(self._extract_industry_levels_from_breadcrumb_text(text))
        return levels

    def _extract_industry(self, rows: list[list[str]], text: str) -> str | None:
        levels = self._extract_industry_levels(rows, text)
        return levels.get("industry_level_3") or levels.get("industry_level_2")

    def _extract_company_name(self, rows: list[list[str]], text: str, symbol: str) -> str | None:
        labeled = self._extract_labeled_value(rows, text, ("ten cong ty", "ten day du", "ten to chuc", "company name"), min_length=4)
        if labeled:
            clean_labeled = clean_company_name(labeled, symbol)
            if clean_labeled:
                return clean_labeled
        title_match = re.search(rf"\b{re.escape(symbol)}\b\s*[-–|:]\s*([^|\n]+)", text, flags=re.IGNORECASE)
        if title_match:
            candidate = clean_company_name(title_match.group(1), symbol)
            if candidate:
                return candidate
        broad_match = re.search(
            r"(?:Ban lãnh đạo\s*&?\s*Sở hữu\s*[-–:|]\s*)?((?:CTCP|Công ty|Ngân hàng|Tổng công ty|Tập đoàn)[^|]{4,220})",
            text,
            flags=re.IGNORECASE,
        )
        if broad_match:
            return clean_company_name(broad_match.group(1), symbol)
        return None

    def _extract_company_name_from_metadata(self, html_text: str, symbol: str) -> str | None:
        candidates: list[str] = []
        for pattern in (
            r'<meta\b[^>]*(?:property|name)=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
            r'<meta\b[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:title["\']',
        ):
            candidates.extend(re.findall(pattern, html_text or "", flags=re.IGNORECASE | re.DOTALL))
        for script_match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text or "", flags=re.IGNORECASE | re.DOTALL):
            raw_json = html_lib.unescape(script_match.group(1) or "").strip()
            raw_json = re.sub(r"(?m)//.*$", "", raw_json)
            try:
                payload = json.loads(raw_json)
            except Exception:
                continue
            candidates.extend(self._metadata_name_candidates(payload))
        for candidate in candidates:
            clean = clean_company_name(candidate, symbol)
            if clean:
                return clean
        return None

    def _metadata_name_candidates(self, payload: Any) -> list[str]:
        candidates: list[str] = []
        if isinstance(payload, list):
            for item in payload:
                candidates.extend(self._metadata_name_candidates(item))
            return candidates
        if not isinstance(payload, dict):
            return candidates
        for key in ("name", "alternateName"):
            value = payload.get(key)
            if isinstance(value, str):
                candidates.append(value)
        about = payload.get("about")
        if isinstance(about, dict):
            candidates.extend(self._metadata_name_candidates(about))
        return candidates

    def _extract_industry_levels_from_breadcrumb_text(self, text: str) -> dict[str, str]:
        normalized = self._normalize_text(text)
        if not any(marker in normalized for marker in ("nganh", "nhom nganh", "linh vuc", "sector", "doanh nghiep trong nganh")):
            return {}
        levels: dict[str, str] = {}
        ordered_terms = [
            ("industry_level_1", (("tai chinh", "Tài chính"), ("cong nghe thong tin", "Công nghệ thông tin"), ("bat dong san", "Bất động sản"))),
            ("industry_level_2", (("to chuc tin dung", "Tổ chức tín dụng"), ("vat lieu xay dung", "Vật liệu xây dựng"))),
            ("industry_level_3", (("ngan hang", "Ngân hàng"), ("thep", "Thép"))),
        ]
        for level, candidates in ordered_terms:
            for needle, label in candidates:
                if needle in normalized:
                    levels.setdefault(level, label)
                    break
        return levels

    def _looks_like_industry_value(self, value: Any) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" :-–—|")
        if len(text) < 2 or len(text) > 160:
            return False
        normalized = self._normalize_text(text)
        forbidden = ("bang gia", "danh muc", "dang nhap", "thoat", "moi nhat", "doc nhanh")
        return not any(term in normalized for term in forbidden)

    def _extract_labeled_value(
        self,
        rows: list[list[str]],
        text: str,
        labels: tuple[str, ...],
        *,
        min_length: int = 2,
    ) -> str | None:
        for row in rows:
            if len(row) < 2:
                continue
            left = self._normalize_text(row[0])
            if any(label in left for label in labels):
                value = " ".join(cell for cell in row[1:] if cell).strip()
                if len(value) >= min_length:
                    return value[:600]
        normalized_labels = "|".join(re.escape(label) for label in labels)
        pattern = re.compile(rf"(?:{normalized_labels})\s*[:\-]\s*(.{{{min_length},600}}?)(?:\s{{2,}}|$)", flags=re.IGNORECASE)
        normalized_text = self._normalize_text(text)
        match = pattern.search(normalized_text)
        if match:
            return match.group(1).strip()[:600]
        return None

    def _extract_people_table(self, tables: list[list[list[str]]], *, table_kind: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for table in tables:
            header_map, header_index = self._people_header_map(table[:4], table_kind=table_kind)
            if not header_map:
                continue
            for row in table[header_index + 1 : header_index + 12]:
                name = self._cell(row, header_map.get("name"))
                if not name or self._is_people_header_value(name):
                    continue
                item: dict[str, Any] = {"source": self.source_name}
                if table_kind == "ownership":
                    item["holder"] = name
                    item["name"] = name
                else:
                    item["name"] = name
                title = self._cell(row, header_map.get("title"))
                shares = self._cell(row, header_map.get("shares"))
                ratio = self._cell(row, header_map.get("ratio"))
                if title and table_kind == "leadership":
                    item["position"] = title
                    item["title"] = title
                if shares:
                    item["shares"] = shares
                if ratio:
                    item["ownership_percent"] = ratio
                    item["ratio"] = ratio
                result.append(item)
        return result[:8]

    def _people_header_map(self, candidate_rows: list[list[str]], *, table_kind: str) -> tuple[dict[str, int], int]:
        for row_index, row in enumerate(candidate_rows):
            mapping: dict[str, int] = {}
            for index, header in enumerate(row):
                normalized = self._normalize_text(header)
                if any(label in normalized for label in ("ho ten", "ten", "co dong", "lanh dao")):
                    mapping.setdefault("name", index)
                if any(label in normalized for label in ("chuc vu", "vi tri")):
                    mapping.setdefault("title", index)
                if any(label in normalized for label in ("so co phieu", "co phieu", "khoi luong", "sl cp", "so cp")) and "ty le" not in normalized:
                    mapping.setdefault("shares", index)
                if any(label in normalized for label in ("ty le", "%")):
                    mapping.setdefault("ratio", index)
            if table_kind == "leadership" and "name" in mapping and "title" in mapping:
                return mapping, row_index
            if table_kind == "ownership" and "name" in mapping and ("shares" in mapping or "ratio" in mapping):
                return mapping, row_index
        return {}, -1

    def _is_people_header_value(self, value: Any) -> bool:
        normalized = self._normalize_text(value)
        return normalized in {"ho ten", "ten", "co dong", "lanh dao", "ten co dong"}

    def _has_useful_company_data(self, result: dict[str, Any]) -> bool:
        return any(
            result.get(key)
            for key in (
                "company_name",
                "industry",
                "sector",
                "industry_level_1",
                "industry_level_2",
                "industry_level_3",
                "business_overview",
                "leadership",
                "ownership",
            )
        )

    def _accepted_company_fields(
        self,
        *,
        company_name: str | None,
        industry_level_1: str | None,
        industry_level_2: str | None,
        industry_level_3: str | None,
        business_overview: str | None,
        leadership: list[dict[str, Any]] | None,
        ownership: list[dict[str, Any]] | None,
    ) -> list[str]:
        fields = []
        if company_name:
            fields.append("company_name")
        if industry_level_1:
            fields.append("industry_level_1")
        if industry_level_2:
            fields.append("industry_level_2")
        if industry_level_3:
            fields.append("industry_level_3")
        if business_overview:
            fields.append("business_overview")
        if leadership:
            fields.append("leadership")
        if ownership:
            fields.append("ownership")
        return fields

    def _status_for_fields(self, result: dict[str, Any]) -> str:
        if result.get("status") in {"disabled", "failed"}:
            return str(result.get("status"))
        company_name = result.get("company_name")
        industry_fields = [
            result.get("industry_level_1") or result.get("sector"),
            result.get("industry_level_2"),
            result.get("industry_level_3") or result.get("industry"),
        ]
        industry_count = sum(1 for value in industry_fields if value)
        has_governance = bool(result.get("leadership") or result.get("ownership"))
        has_basic = any([company_name, industry_count, result.get("business_overview")])
        if not any([has_basic, has_governance]):
            return "insufficient"
        if company_name and has_governance:
            return "success"
        return "partial"

    async def _fetch_with_cache(self, url: str, cache_kind: str) -> str:
        cached = self._read_cache(url, cache_kind)
        if cached is not None:
            return cached
        text = await self.http_client.get_text(url, headers={"User-Agent": self.settings.research_user_agent})
        self._write_cache(url, text, cache_kind)
        return text

    def _cache_path(self, url: str, cache_kind: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"cafef_company_{cache_kind}_{digest}.json"

    def _read_cache(self, url: str, cache_kind: str) -> str | None:
        path = self._cache_path(url, cache_kind)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("cached_at") or 0) > self.settings.cafef_company_cache_ttl_seconds:
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
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_company_rendered.html").write_text(scrub_debug_text(html_text), encoding="utf-8")
        except Exception:
            return

    def _save_raw_debug(self, symbol: str, html_text: str) -> None:
        if not (self.settings.external_data_debug_save_rendered_html or self.settings.vietstock_debug_save_rendered_html):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_company_raw.html").write_text(scrub_debug_text(html_text or ""), encoding="utf-8")
        except Exception:
            return

    def _save_extraction_debug(self, symbol: str, source_url: str, result: dict[str, Any], *, render_status: str, html_text: str) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        parser = _TableParser()
        parser.feed(html_text or "")
        debug = result.get("debug") if isinstance(result.get("debug"), dict) else {}
        leadership_rows = result.get("leadership") if isinstance(result.get("leadership"), list) else []
        ownership_rows = result.get("ownership") if isinstance(result.get("ownership"), list) else []
        candidate_sections = self._candidate_sections_from_text(html_text or "")
        payload = {
            "url": source_url,
            "source_url": source_url,
            "http_status": "loaded" if html_text else "empty",
            "used_playwright": "playwright" in render_status or "render" in render_status,
            "parser_mode": render_status,
            "rendered_html_length": len(html_text or ""),
            "tables_found": len(parser.tables),
            "candidate_sections_found": candidate_sections,
            "row_count": len(re.findall(r"(?is)<tr\b", html_text or "")),
            "selectors_found": self._selectors_found(html_text),
            "accepted_fields": result.get("accepted_fields") or [],
            "rejected_fields": result.get("rejected_fields") or [],
            "rejection_reasons": result.get("rejection_reasons") or [],
            "leadership_rows_found": len(leadership_rows),
            "ownership_rows_found": len(ownership_rows),
            "accepted_rows": debug.get("accepted_rows") or [],
            "rejected_rows": debug.get("rejected_rows") or [],
            "final_normalized_data": result,
            "source_status": result.get("status"),
            "final_status": result.get("status"),
            "failure_reason": debug.get("failure_reason") or self._company_failure_reason(leadership_rows, ownership_rows, result.get("company_name")),
            "warnings": result.get("warnings") or [],
            "technical_warnings": result.get("technical_warnings") or [],
        }
        tables_payload = {
            "url": source_url,
            "used_playwright": payload["used_playwright"],
            "tables_found": len(parser.tables),
            "candidate_sections_found": candidate_sections,
            "tables": [
                {"index": index, "rows": table[:20], "row_count": len(table)}
                for index, table in enumerate(parser.tables[:20])
            ],
            "leadership_rows_found": len(leadership_rows),
            "ownership_rows_found": len(ownership_rows),
            "accepted_rows": payload["accepted_rows"],
            "rejected_rows": payload["rejected_rows"],
            "failure_reason": payload["failure_reason"],
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_company_tables.json").write_text(
                json.dumps(scrub_debug_payload(tables_payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_company_extraction.json").write_text(
                json.dumps(scrub_debug_payload(payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_leadership_ownership_normalized.json").write_text(
                json.dumps(
                    scrub_debug_payload(
                        {
                        "symbol": normalize_symbol(symbol),
                        "source_url": source_url,
                        "leadership": result.get("leadership") or [],
                        "ownership": result.get("ownership") or [],
                        "status": result.get("status"),
                        "accepted_fields": result.get("accepted_fields") or [],
                        "rejected_fields": result.get("rejected_fields") or [],
                        }
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_url_debug(
        self,
        symbol: str,
        source_url: str,
        result: dict[str, Any],
        *,
        http_status: str,
        parser_mode: str,
        render_status: str | None = None,
    ) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        symbol_in_url = self._symbol_from_company_url(source_url)
        exchange_in_url = self._exchange_from_company_url(source_url)
        payload = {
            "final_cafef_url": source_url,
            "source_url": source_url,
            "symbol_used_in_url": symbol_in_url,
            "exchange_used_in_url": exchange_in_url,
            "symbol_is_lowercase": bool(symbol_in_url and symbol_in_url == symbol_in_url.lower()),
            "http_status": http_status,
            "render_status": render_status or parser_mode,
            "parser_mode": parser_mode,
            "selectors_found": result.get("selectors_found") or [],
            "accepted_fields": result.get("accepted_fields") or [],
            "rejected_fields": result.get("rejected_fields") or [],
            "rejection_reasons": result.get("rejection_reasons") or [],
            "final_normalized_company_overview": {
                key: result.get(key)
                for key in (
                    "symbol",
                    "company_name",
                    "exchange",
                    "industry_level_1",
                    "industry_level_2",
                    "industry_level_3",
                    "business_overview",
                    "leadership",
                    "ownership",
                    "source",
                    "source_url",
                    "confidence",
                    "status",
                )
                if result.get(key) not in (None, "", [], {})
            },
            "requested_symbol": normalize_symbol(symbol),
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_company_url.json").write_text(
                json.dumps(scrub_debug_payload(payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_cafef_company_request.json").write_text(
                json.dumps(scrub_debug_payload(payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _selectors_found(self, html_text: str) -> list[str]:
        found = []
        checks = (
            ("table", r"(?is)<table\b"),
            ("company_heading", r"(?is)<h[1-3]\b"),
            ("meta_og_title", r"(?is)<meta\b[^>]*(?:property|name)=['\"]og:title['\"]"),
            ("json_ld", r"(?is)<script[^>]+type=['\"]application/ld\+json['\"]"),
            ("leadership_text", r"Ban\s+lãnh\s+đạo"),
            ("ownership_text", r"Sở\s+hữu"),
        )
        for label, pattern in checks:
            if re.search(pattern, html_text or ""):
                found.append(label)
        return found

    def _candidate_sections_from_text(self, html_text: str) -> list[str]:
        text = self._clean_html_text(html_text)
        markers = ("Ban lãnh đạo", "Lãnh đạo", "Hội đồng quản trị", "Ban giám đốc", "Ban kiểm soát", "Sở hữu", "Cổ đông")
        found: list[str] = []
        for marker in markers:
            if marker.lower() in text.lower():
                found.append(marker)
        return found

    def _symbol_from_company_url(self, source_url: str) -> str | None:
        match = re.search(r"/du-lieu/[^/]+/([a-z0-9]+)-ban-lanh-dao-so-huu\.chn", source_url or "", flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _exchange_from_company_url(self, source_url: str) -> str | None:
        match = re.search(r"/du-lieu/([^/]+)/[a-z0-9]+-ban-lanh-dao-so-huu\.chn", source_url or "", flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _result(
        self,
        *,
        source_url: str,
        status: str,
        warnings: list[str],
        symbol: str | None = None,
        exchange: str | None = None,
        company_name: str | None = None,
        industry: str | None = None,
        sector: str | None = None,
        industry_level_1: str | None = None,
        industry_level_2: str | None = None,
        industry_level_3: str | None = None,
        business_overview: str | None = None,
        leadership: list[dict[str, Any]] | None = None,
        ownership: list[dict[str, Any]] | None = None,
        technical_warnings: list[str] | None = None,
        accepted_fields: list[str] | None = None,
        rejected_fields: list[str] | None = None,
        rejection_reasons: list[str] | None = None,
        selectors_found: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "company_name": company_name,
            "exchange": exchange,
            "industry_level_1": industry_level_1,
            "industry_level_2": industry_level_2,
            "industry_level_3": industry_level_3,
            "industry": industry,
            "sector": sector,
            "business_overview": business_overview,
            "leadership": leadership or [],
            "ownership": ownership or [],
            "source": self.source_name,
            "source_url": source_url,
            "confidence": self._confidence(
                company_name=company_name,
                industry_level_1=industry_level_1,
                industry_level_2=industry_level_2,
                industry_level_3=industry_level_3,
                business_overview=business_overview,
                leadership=leadership,
                ownership=ownership,
            ),
            "fetched_at": now_iso(),
            "status": status,
            "warnings": _dedupe_preserve_order(warnings),
            "technical_warnings": _dedupe_preserve_order(technical_warnings or []),
            "accepted_fields": _dedupe_preserve_order(accepted_fields or []),
            "rejected_fields": _dedupe_preserve_order(rejected_fields or []),
            "rejection_reasons": _dedupe_preserve_order(rejection_reasons or []),
            "selectors_found": _dedupe_preserve_order(selectors_found or []),
        }

    def _confidence(
        self,
        *,
        company_name: str | None,
        industry_level_1: str | None,
        industry_level_2: str | None,
        industry_level_3: str | None,
        business_overview: str | None,
        leadership: list[dict[str, Any]] | None,
        ownership: list[dict[str, Any]] | None,
    ) -> float:
        score = 0.35
        if company_name:
            score += 0.2
        if industry_level_1:
            score += 0.08
        if industry_level_2:
            score += 0.08
        if industry_level_3:
            score += 0.08
        if business_overview:
            score += 0.1
        if leadership:
            score += 0.05
        if ownership:
            score += 0.04
        return round(min(score, 0.85), 2)

    def _clean_html_text(self, html_text: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text or "")
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()

    def _normalize_text(self, value: Any) -> str:
        normalized = unicodedata.normalize("NFD", str(value or ""))
        normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
        normalized = normalized.lower().replace("đ", "d")
        normalized = re.sub(r"[^a-z0-9/%\s.-]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _cell(self, row: list[str], index: int | None) -> str | None:
        if index is None or index < 0 or index >= len(row):
            return None
        clean = str(row[index] or "").strip()
        return clean or None

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _as_list(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return [str(value)]

    def _as_list_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _merge_string_lists(self, *values: list[str]) -> list[str]:
        merged: list[str] = []
        for group in values:
            merged.extend(group)
        return _dedupe_preserve_order(merged)

    def _exchange_from_center_id(self, value: Any) -> str | None:
        try:
            center_id = int(value)
        except (TypeError, ValueError):
            return None
        return {1: "HOSE", 2: "HNX", 9: "UPCOM", 8: "OTC"}.get(center_id)

    def _clean_person_or_holder(self, value: Any) -> str | None:
        text = self._clean_html_text(str(value or ""))
        text = re.sub(r"\s+", " ", text).strip(" -–—|:")
        if not text:
            return None
        normalized = self._normalize_text(text)
        forbidden = ("bang gia", "danh muc", "dang nhap", "moi nhat", "doc nhanh", "xep hang", "tin hieu")
        if any(term in normalized for term in forbidden):
            return None
        if len(text) < 2 or len(text) > 180:
            return None
        return text

    def _normalize_ownership_percent(self, value: Any) -> str | None:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return None
        text = text.replace(".", "#DOT#").replace(",", ".") if "," in text and "." not in text else text
        text = text.replace("#DOT#", ".")
        text = text.strip("% ")
        try:
            number = float(text)
        except ValueError:
            clean = str(value or "").strip()
            return clean if clean.endswith("%") else None
        if number < 0:
            return None
        if float(number).is_integer():
            return f"{int(number)}%"
        return f"{number:.4f}".rstrip("0").rstrip(".") + "%"

    def _ownership_rate_value(self, value: Any) -> float:
        text = str(value or "").replace("%", "").replace(",", ".").strip()
        try:
            return float(text)
        except ValueError:
            return -1.0

    def _dedupe_people(self, rows: list[dict[str, Any]], *, identity_keys: tuple[str, ...]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            identity = tuple(self._normalize_text(row.get(key)) for key in identity_keys)
            if not any(identity) or identity in seen:
                continue
            seen.add(identity)
            result.append(row)
        return result

    def _company_failure_reason(self, leadership: list[dict[str, Any]], ownership: list[dict[str, Any]], company_name: Any) -> str | None:
        missing = []
        if not company_name:
            missing.append("company_name")
        if not leadership:
            missing.append("leadership")
        if not ownership:
            missing.append("ownership")
        if not missing:
            return None
        return "CafeF extraction còn thiếu: " + ", ".join(missing)
