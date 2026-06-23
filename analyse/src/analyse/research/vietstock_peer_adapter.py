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
from analyse.research.vietstock_financial_adapter import _TableParser
from analyse.research.vietstock_financial_adapter import _dedupe_preserve_order
from analyse.utils.asyncio_windows import ensure_windows_proactor_event_loop_policy
from analyse.utils.asyncio_windows import run_in_windows_proactor_thread
from analyse.utils.datetime_utils import now_iso
from analyse.utils.playwright_safe import PlaywrightTimeoutError
from analyse.utils.playwright_safe import TargetClosedError
from analyse.utils.playwright_safe import cancel_pending_tasks_safely
from analyse.utils.playwright_safe import close_playwright_objects_safely
from analyse.utils.playwright_safe import gather_safely
from analyse.utils.playwright_safe import is_playwright_timeout_error
from analyse.utils.playwright_safe import is_target_closed_error
from analyse.utils.playwright_safe import remove_playwright_listener_safely
from analyse.utils.playwright_safe import safe_playwright_error_message
from analyse.utils.playwright_safe import save_playwright_error_debug
from analyse.utils.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


class PlaywrightVietstockPeerRenderer:
    """Render Vietstock same-industry peer page when static HTML is incomplete."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_rendered_html(self, url: str) -> tuple[str | None, list[str]]:
        ensure_windows_proactor_event_loop_policy()
        return await run_in_windows_proactor_thread(lambda: self._fetch_rendered_html_direct(url))

    async def _fetch_rendered_html_direct(self, url: str) -> tuple[str | None, list[str]]:
        try:
            playwright_api = importlib.import_module("playwright.async_api")
        except ImportError:
            return None, ["Playwright chưa được cài đặt hoặc Chromium chưa sẵn sàng cho peer fallback."]

        async_playwright = playwright_api.async_playwright
        captured_payloads: list[str] = []
        pending_tasks: list[asyncio.Task[Any]] = []
        browser = None
        context = None
        page = None
        label = "playwright:vietstock-peer"
        response_handler = None
        debug_error: BaseException | None = None
        debug_phase = "unknown"
        try:
            async with async_playwright() as playwright:
                logger.info("[%s] launch browser", label)
                browser = await playwright.chromium.launch(headless=self.settings.vietstock_peer_browser_headless)
                context = await browser.new_context(
                    viewport={
                        "width": self.settings.vietstock_peer_browser_viewport_width,
                        "height": self.settings.vietstock_peer_browser_viewport_height,
                    },
                    user_agent=self.settings.research_user_agent,
                )
                page = await context.new_page()

                async def capture_response(response: Any) -> None:
                    try:
                        response_url = str(response.url or "")
                        content_type = (response.headers or {}).get("content-type", "")
                        if "json" not in content_type.lower() and "Screener/FilterForRelationCompany" not in response_url:
                            return
                        text = await response.text()
                        haystack = f"{response_url} {text[:5000]}".lower()
                        if any(marker in haystack for marker in ("symbol", "stock", "pe", "pb", "roe", "ticker", "filterforrelationcompany", "stockcode")):
                            captured_payloads.append(json.dumps({"url": response_url, "payload": text[:500_000]}, ensure_ascii=False))
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
                timeout_ms = max(self.settings.vietstock_peer_timeout_ms, 60000)
                wait_until = self._safe_wait_until(self.settings.vietstock_peer_browser_wait_until)
                logger.info("[%s] goto URL", label)
                await self._goto_safely(page, url, wait_until=wait_until, timeout_ms=timeout_ms)
                await self._wait_for_peer_content(page)
                if self.settings.vietstock_peer_browser_extra_wait_ms > 0:
                    await page.wait_for_timeout(self.settings.vietstock_peer_browser_extra_wait_ms)
                if pending_tasks:
                    results = await gather_safely(pending_tasks, label=label)
                    for result in results:
                        if isinstance(result, BaseException) and debug_error is None:
                            debug_error = result
                            debug_phase = "response_handler"
                logger.info("[%s] extract table", label)
                html_parts = [await page.content()]
                default_tab_html = await self._collect_default_tab_content(page)
                if default_tab_html:
                    html_parts.append(default_tab_html)
                dom_payload = await self._extract_dom_payload(page)
                html_text = "\n".join(html_parts)
                if captured_payloads:
                    payload_tags = "".join(
                        f'<script type="application/json" data-vietstock-peer-xhr>{html_lib.escape(payload)}</script>'
                        for payload in captured_payloads[:5]
                    )
                    html_text += payload_tags
                if dom_payload:
                    html_text += (
                        '<script type="application/json" data-vietstock-peer-dom>'
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
            return None, [f"Vietstock peer rendering failed: TargetClosedError: {message}"]
        except PlaywrightTimeoutError as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            debug_phase = "goto/extract"
            message = safe_playwright_error_message(exc)
            logger.warning("[%s] Playwright timeout: %s", label, message)
            return None, [f"Vietstock peer rendering failed: TimeoutError: {message}"]
        except Exception as exc:  # pragma: no cover - host/browser dependent
            debug_error = exc
            debug_phase = "goto/extract"
            if is_target_closed_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright target closed: %s", label, message)
                return None, [f"Vietstock peer rendering failed: TargetClosedError: {message}"]
            if is_playwright_timeout_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright timeout: %s", label, message)
                return None, [f"Vietstock peer rendering failed: TimeoutError: {message}"]
            logger.warning("[%s] Playwright crawler failed safely: %s", label, exc, exc_info=True)
            return None, [f"Vietstock peer rendering failed: {exc.__class__.__name__}: {self._safe_error_message(exc)}"]
        finally:
            if response_handler is not None:
                remove_playwright_listener_safely(page, "response", response_handler, label=label)
            logger.info("[%s] pending tasks count=%s", label, len([task for task in pending_tasks if not task.done()]))
            await cancel_pending_tasks_safely(pending_tasks, label=label)
            await close_playwright_objects_safely(page=page, context=context, browser=browser, label=label)
            if debug_error is not None:
                save_playwright_error_debug(
                    self.settings,
                    source="Vietstock peer",
                    url=url,
                    slug="vietstock_peer",
                    error=debug_error,
                    phase=debug_phase,
                    pending_tasks_count=len([task for task in pending_tasks if not task.done()]),
                    cleanup_completed=True,
                )
            logger.info("[%s] cleanup completed", label)

    def _safe_wait_until(self, value: str | None) -> str:
        wait_until = (value or "domcontentloaded").strip().lower()
        if wait_until == "networkidle":
            return "domcontentloaded"
        if wait_until not in {"commit", "domcontentloaded", "load"}:
            return "domcontentloaded"
        return wait_until

    async def _goto_safely(self, page: Any, url: str, *, wait_until: str, timeout_ms: int) -> None:
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        except Exception:
            try:
                content = await page.content()
                if content and len(content) > 500:
                    return
            except Exception:
                pass
            raise

    async def _collect_default_tab_content(self, page: Any) -> str | None:
        label = self.settings.vietstock_peer_default_tab or "Tổng quan"
        clicked = await self._try_click_tab(page, label)
        if not clicked:
            return None
        try:
            await page.wait_for_timeout(900)
            await self._wait_for_peer_content(page)
            return await page.content()
        except Exception:
            return None

    async def _try_click_tab(self, page: Any, label: str) -> bool:
        candidates = [
            f"role=tab[name='{label}']",
            f"text={label}",
            f"a:has-text('{label}')",
            f"button:has-text('{label}')",
        ]
        for selector in candidates:
            try:
                locator = page.locator(selector).first()
                if await locator.count() <= 0:
                    continue
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=1500)
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_peer_content(self, page: Any) -> None:
        selector = (self.settings.vietstock_peer_browser_wait_selector or "").strip()
        selectors = [selector] if selector else [
            "table",
            "text=Cùng ngành",
            "text=Mã chứng khoán",
            "text=Giá đóng cửa",
            "text=KL khớp lệnh",
            "text=GT khớp lệnh",
            "text=Tín hiệu mua bán",
            "text=P/E",
            "text=RSI",
            "[class*=compare]",
            "[id*=compare]",
            "[class*=industry]",
            "[id*=industry]",
        ]
        timeout = min(max(self.settings.vietstock_peer_timeout_ms // 4, 2000), 7000)
        for candidate in selectors:
            try:
                await page.wait_for_selector(candidate, timeout=timeout)
                return
            except Exception:
                continue

    async def _extract_dom_payload(self, page: Any) -> dict[str, Any] | None:
        try:
            return await page.evaluate(
                """() => {
                    const textOf = el => (el && (el.innerText || el.textContent) || '').replace(/\\s+/g, ' ').trim();
                    const tables = Array.from(document.querySelectorAll('table')).map((table, index) => ({
                        index,
                        className: String(table.className || ''),
                        headers: Array.from(table.querySelectorAll('thead th, tr:first-child th, tr:first-child td')).map(textOf),
                        rows: Array.from(table.querySelectorAll('tbody tr, tr')).slice(0, 160).map(row =>
                            Array.from(row.querySelectorAll('td, th')).map(textOf)
                        ),
                        text: textOf(table).slice(0, 2400)
                    }));
                    const grids = Array.from(document.querySelectorAll('[role="row"], .table-row, .stock-row, .compare-row, .ag-row, .slick-row, .k-master-row')).map((row, index) => ({
                        index,
                        tag: row.tagName,
                        className: String(row.className || ''),
                        text: textOf(row).slice(0, 1600),
                        cells: Array.from(row.querySelectorAll('[role="cell"], .cell, td, th, div, span')).map(textOf).filter(Boolean).slice(0, 40)
                    })).filter(item => /Mã chứng khoán|P\\/E|Vốn hóa|EPS|\\b[A-Z]{3}\\b/.test(item.text)).slice(0, 160);
                    return {title: document.title, url: location.href, tables, grids};
                }"""
            )
        except Exception:
            return None

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        if len(message) > 180:
            message = message[:177].rstrip() + "..."
        return message or "không có thông điệp chi tiết"


class VietstockPeerAdapter:
    source_name = "Vietstock Finance"
    user_source_name = "Vietstock peer cùng ngành"

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: HttpClient | None = None,
        browser_renderer: PlaywrightVietstockPeerRenderer | Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client or HttpClient(timeout_ms=self.settings.vietstock_peer_timeout_ms)
        self.browser_renderer = browser_renderer or PlaywrightVietstockPeerRenderer(self.settings)
        self.cache_dir = Path(self.settings.research_cache_dir)

    async def fetch(self, symbol: str) -> dict[str, Any]:
        clean_symbol = normalize_symbol(symbol)
        source_url = self.settings.vietstock_peer_url_template.format(symbol=clean_symbol)
        if not self.settings.enable_vietstock_peer_fallback:
            return self._result(source_url, [], ["Peer fallback Vietstock đang tắt theo cấu hình."], [], "disabled")

        warnings: list[str] = []
        technical_warnings: list[str] = []
        try:
            html_text = await self._fetch_with_cache(source_url, cache_kind="static")
            self._save_raw_debug(clean_symbol, html_text)
        except Exception as exc:
            warnings.append("Dữ liệu peer công khai chưa sẵn sàng trong lần chạy này.")
            technical_warnings.append(f"Vietstock peer static fetch failed: {exc.__class__.__name__}: {exc}")
            result = self._result(source_url, [], warnings, technical_warnings, "failed")
            self._save_request_debug(clean_symbol, source_url, result, http_status="failed", render_status="static_fetch_failed")
            return result

        parsed = self.parse_html(html_text, source_url=source_url, symbol=clean_symbol)
        static_industry = parsed.get("industry") if isinstance(parsed, dict) else {}
        if parsed.get("peers"):
            self._save_extraction_debug(clean_symbol, source_url, parsed, render_status="static_success", html_text=html_text)
            self._save_request_debug(clean_symbol, source_url, parsed, http_status="loaded", render_status="static_success")
            return parsed

        warnings.extend(self._as_list(parsed.get("warnings")))
        technical_warnings.extend(self._as_list(parsed.get("technical_warnings")))
        warnings.append("Chưa trích xuất đủ peer từ nội dung tĩnh, chuyển sang đối chiếu bằng trình duyệt.")

        if not self.settings.vietstock_peer_use_browser_fallback:
            warnings.append("Peer browser fallback Vietstock đang tắt theo cấu hình.")
            return self._result(
                source_url,
                [],
                _dedupe_preserve_order(warnings),
                _dedupe_preserve_order(technical_warnings),
                "insufficient",
                industry=static_industry if isinstance(static_industry, dict) else None,
                debug=parsed.get("debug") if isinstance(parsed, dict) else None,
            )

        rendered_html = self._read_cache(source_url, cache_kind="rendered")
        if rendered_html is None:
            rendered_html, browser_warnings = await self.browser_renderer.fetch_rendered_html(source_url)
            warnings.extend(browser_warnings)
            technical_warnings.extend(browser_warnings)
            if rendered_html:
                self._write_cache(source_url, rendered_html, cache_kind="rendered")
                self._save_rendered_debug(clean_symbol, rendered_html)

        if not rendered_html:
            result = self._result(
                source_url,
                [],
                _dedupe_preserve_order(warnings),
                _dedupe_preserve_order(technical_warnings),
                "failed",
                industry=static_industry if isinstance(static_industry, dict) else None,
            )
            self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_failed", html_text="")
            self._save_request_debug(clean_symbol, source_url, result, http_status="loaded", render_status="render_failed")
            return result

        rendered_parsed = self.parse_html(rendered_html, source_url=source_url, symbol=clean_symbol)
        peers = rendered_parsed.get("peers") or []
        warnings.extend(self._as_list(rendered_parsed.get("warnings")))
        technical_warnings.extend(self._as_list(rendered_parsed.get("technical_warnings")))
        if peers:
            status = rendered_parsed.get("status") or self._peer_status(peers)
            result = self._result(
                source_url,
                peers,
                _dedupe_preserve_order(warnings),
                _dedupe_preserve_order(technical_warnings),
                status,
                industry=(rendered_parsed.get("industry") or static_industry) if isinstance(rendered_parsed, dict) else static_industry,
                debug=rendered_parsed.get("debug") if isinstance(rendered_parsed, dict) else None,
            )
            self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_success", html_text=rendered_html)
            self._save_request_debug(clean_symbol, source_url, result, http_status="loaded", render_status="render_success")
            return result
        warnings.append("Đã thử đối chiếu Vietstock Finance nhưng chưa trích xuất đủ peer cùng ngành.")
        result = self._result(
            source_url,
            [],
            _dedupe_preserve_order(warnings),
            _dedupe_preserve_order(technical_warnings),
            "insufficient",
            industry=rendered_parsed.get("industry") or static_industry if isinstance(rendered_parsed, dict) else static_industry,
            debug=rendered_parsed.get("debug") if isinstance(rendered_parsed, dict) else None,
        )
        self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_partial", html_text=rendered_html)
        self._save_request_debug(clean_symbol, source_url, result, http_status="loaded", render_status="render_partial")
        return result

    def parse_html(self, html_text: str, *, source_url: str, symbol: str) -> dict[str, Any]:
        peers: list[dict[str, Any]] = []
        parser = _TableParser()
        parser.feed(html_text or "")
        industry = self._extract_industry_context(html_text or "", source_url=source_url)
        debug_info = self._debug_table_snapshot(parser.tables)
        for table in parser.tables:
            peers.extend(self._parse_table(table, source_url=source_url))
        peers.extend(self._parse_json_payloads(html_text or "", source_url=source_url))
        dom_payload = self._parse_dom_payloads(html_text or "")
        if dom_payload:
            debug_info["dom_tables_found"] = len(dom_payload.get("tables") or [])
            debug_info["grid_rows_found"] = len(dom_payload.get("grids") or [])
            for table in dom_payload.get("tables") or []:
                if isinstance(table, dict):
                    rows = table.get("rows")
                    if isinstance(rows, list):
                        peers.extend(self._parse_table(rows, source_url=source_url))
            for grid in dom_payload.get("grids") or []:
                if isinstance(grid, dict):
                    cells = grid.get("cells")
                    if isinstance(cells, list):
                        peer = self._row_to_peer([str(cell) for cell in cells], header_map={}, source_url=source_url)
                        if peer:
                            peer["verified_row_evidence"] = "dom_grid"
                            peers.append(peer)
        peers.extend(self._parse_stock_link_rows(html_text or "", source_url=source_url))
        peers = self._finalize_peers(peers, symbol=symbol)
        debug_info["normalized_rows"] = peers
        debug_info["normalized_peers_count"] = len(peers)
        debug_info["tab_selected"] = self.settings.vietstock_peer_default_tab or "Tổng quan"
        warnings = [] if peers else ["Chưa tìm thấy bảng peer cùng ngành đủ điều kiện từ Vietstock Finance."]
        if industry and not peers:
            warnings = ["Đã nhận diện được nhóm ngành nhưng chưa trích xuất đủ dòng peer định lượng từ Vietstock Finance."]
        status = self._peer_status(peers)
        if not peers:
            debug_info["failure_reason"] = self._peer_failure_reason(debug_info)
        return self._result(source_url, peers, warnings, [], status, industry=industry, debug=debug_info)

    def _parse_table(self, table: list[list[str]], *, source_url: str) -> list[dict[str, Any]]:
        header_index = None
        header_map: dict[str, int] = {}
        for index, row in enumerate(table[:8]):
            mapped = self._header_map(row)
            if "symbol" in mapped and self._is_overview_header(mapped):
                header_index = index
                header_map = mapped
                break
        rows = table[(header_index + 1) if header_index is not None else 0 :]
        peers: list[dict[str, Any]] = []
        for row in rows:
            peer = self._row_to_peer(row, header_map=header_map, source_url=source_url)
            if peer:
                peers.append(peer)
        return peers

    def _row_to_peer(self, row: list[str], *, header_map: dict[str, int], source_url: str) -> dict[str, Any] | None:
        if not row:
            return None
        symbol_cell = self._cell(row, header_map.get("symbol"))
        symbol = self._symbol_from_symbol_company_cell(symbol_cell)
        if not symbol:
            for cell in row[:3]:
                parsed_symbol = self._symbol_from_symbol_company_cell(cell)
                if parsed_symbol:
                    symbol = parsed_symbol
                    break
        if not symbol or not self._looks_like_symbol(symbol):
            return None
        company = self._clean_peer_company_candidate(self._cell(row, header_map.get("company")), symbol)
        if not company:
            for cell in row[:4]:
                company = self._company_from_symbol_company_cell(cell, symbol)
                if company:
                    break
        peer = {
            "symbol": normalize_symbol(symbol),
            "company": company,
            "exchange": self._cell(row, header_map.get("exchange")),
            "industry": self._cell(row, header_map.get("industry")),
            "close_price": self._parse_number(self._cell(row, header_map.get("close_price"))),
            "change_1d_percent": self._parse_number(self._cell(row, header_map.get("change_1d_percent"))),
            "matched_volume": self._parse_number(self._cell(row, header_map.get("matched_volume"))),
            "matched_value_billion": self._parse_number(self._cell(row, header_map.get("matched_value_billion"))),
            "fundamental_rating": self._cell(row, header_map.get("fundamental_rating")),
            "buy_sell_signal": self._cell(row, header_map.get("buy_sell_signal")),
            "market_cap_billion": self._parse_number(self._cell(row, header_map.get("market_cap_billion"))),
            "eps_4q": self._parse_number(self._cell(row, header_map.get("eps_4q"))),
            "pe_basic": self._parse_number(self._cell(row, header_map.get("pe_basic"))),
            "macd": self._parse_number(self._cell(row, header_map.get("macd"))),
            "rsi_14": self._parse_number(self._cell(row, header_map.get("rsi_14"))),
            "stoch_rsi": self._parse_number(self._cell(row, header_map.get("stoch_rsi"))),
            "basic_score": self._parse_number(self._cell(row, header_map.get("basic_score"))),
            "first_trading_date": self._cell(row, header_map.get("first_trading_date")),
            "price": self._parse_number(self._cell(row, header_map.get("close_price"))),
            "market_cap": self._parse_number(self._cell(row, header_map.get("market_cap_billion"))),
            "pe": self._parse_number(self._cell(row, header_map.get("pe_basic"))),
            "pb": self._parse_number(self._cell(row, header_map.get("pb"))),
            "roe": self._parse_number(self._cell(row, header_map.get("roe"))),
            "revenue": self._parse_number(self._cell(row, header_map.get("revenue"))),
            "profit_after_tax": self._parse_number(self._cell(row, header_map.get("profit_after_tax"))),
            "net_margin": self._parse_number(self._cell(row, header_map.get("net_margin"))),
            "momentum_1m": self._parse_number(self._cell(row, header_map.get("momentum_1m"))),
            "liquidity": self._parse_number(self._cell(row, header_map.get("liquidity"))),
            "source": self.source_name,
            "source_url": source_url,
            "same_industry_reason": "Xuất hiện trong bảng so sánh cùng ngành của Vietstock Finance.",
            "verified_row_evidence": "table",
            "confidence": 0.75,
        }
        return {key: value for key, value in peer.items() if value not in (None, "")}

    def _header_map(self, row: list[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        for index, header in enumerate(row):
            normalized = self._normalize_text(header)
            if not normalized or normalized in {"stt", "#"}:
                continue
            if "macd" in normalized:
                result.setdefault("macd", index)
                continue
            if "stoch rsi" in normalized:
                result.setdefault("stoch_rsi", index)
                continue
            if "rsi" in normalized:
                result.setdefault("rsi_14", index)
                continue
            if normalized in {"ma", "ma ck", "ticker", "symbol"} or "ma chung khoan" in normalized:
                result.setdefault("symbol", index)
                continue
            if any(label in normalized for label in ("doanh nghiep", "ten cong ty", "cong ty")) or normalized == "ten":
                result.setdefault("company", index)
                continue
            if normalized in {"san", "exchange"}:
                result.setdefault("exchange", index)
                continue
            if "nhom nganh" in normalized or normalized == "nganh":
                result.setdefault("industry", index)
                continue
            if "gia dong cua" in normalized or normalized in {"gia", "thi gia"}:
                result.setdefault("close_price", index)
                continue
            if "% thay doi 1d" in normalized or "thay doi 1d" in normalized or "% 1d" in normalized:
                result.setdefault("change_1d_percent", index)
                continue
            if "kl khop lenh" in normalized or "khoi luong khop lenh" in normalized:
                result.setdefault("matched_volume", index)
                continue
            if "gt khop lenh" in normalized or "gia tri khop lenh" in normalized:
                result.setdefault("matched_value_billion", index)
                continue
            if "xep hang co ban" in normalized or normalized == "xep hang":
                result.setdefault("fundamental_rating", index)
                continue
            if "tin hieu mua ban" in normalized or normalized == "tin hieu":
                result.setdefault("buy_sell_signal", index)
                continue
            if "von hoa" in normalized or "market cap" in normalized:
                result.setdefault("market_cap_billion", index)
                continue
            if "eps 4 quy" in normalized or "eps 4q" in normalized:
                result.setdefault("eps_4q", index)
                continue
            if "p/e co ban" in normalized or normalized in {"p/e", "pe co ban", "pe"}:
                result.setdefault("pe_basic", index)
                continue
            if normalized in {"p/b", "pb"}:
                result.setdefault("pb", index)
                continue
            if normalized == "roe":
                result.setdefault("roe", index)
                continue
            if "diem co ban" in normalized:
                result.setdefault("basic_score", index)
                continue
            if "ngay gd dau tien" in normalized or "ngay giao dich dau tien" in normalized:
                result.setdefault("first_trading_date", index)
                continue
            if "doanh thu" in normalized:
                result.setdefault("revenue", index)
                continue
            if "loi nhuan sau thue" in normalized or normalized == "lnst":
                result.setdefault("profit_after_tax", index)
                continue
            if "bien loi nhuan" in normalized or "net margin" in normalized:
                result.setdefault("net_margin", index)
                continue
            if normalized in {"1m", "1 thang", "mot thang"}:
                result.setdefault("momentum_1m", index)
                continue
            if "thanh khoan" in normalized or normalized == "volume" or normalized == "khoi luong":
                result.setdefault("liquidity", index)
                continue
        return result

    def _is_overview_header(self, header_map: dict[str, int]) -> bool:
        useful = {
            "close_price",
            "change_1d_percent",
            "matched_volume",
            "matched_value_billion",
            "fundamental_rating",
            "buy_sell_signal",
            "market_cap_billion",
            "eps_4q",
            "pe_basic",
            "macd",
            "rsi_14",
            "basic_score",
        }
        return len(useful.intersection(header_map)) >= 2

    def _parse_json_payloads(self, html_text: str, *, source_url: str) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        for match in re.findall(r'<script[^>]*data-vietstock-peer-xhr[^>]*>(.*?)</script>', html_text, flags=re.IGNORECASE | re.DOTALL):
            text = html_lib.unescape(match)
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("payload"), str):
                try:
                    payload = json.loads(payload.get("payload") or "{}")
                except json.JSONDecodeError:
                    continue
            peers.extend(self._extract_peers_from_json(payload, source_url=source_url))
        return peers

    def _parse_dom_payloads(self, html_text: str) -> dict[str, Any]:
        match = re.search(r'<script[^>]*data-vietstock-peer-dom[^>]*>(.*?)</script>', html_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(html_lib.unescape(match.group(1) or ""))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _extract_peers_from_json(self, payload: Any, *, source_url: str) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        if isinstance(payload, list):
            for item in payload:
                peers.extend(self._extract_peers_from_json(item, source_url=source_url))
        elif isinstance(payload, dict):
            symbol = payload.get("symbol") or payload.get("stockCode") or payload.get("ticker") or payload.get("code")
            if symbol and self._looks_like_symbol(symbol):
                relation_metrics = self._relation_company_metrics(payload)
                close_price = self._parse_number(payload.get("close_price") or payload.get("closePrice") or payload.get("price") or payload.get("close"))
                if close_price is None:
                    close_price = self._parse_number(payload.get("BasicPriceInit") or payload.get("basicPriceInit"))
                market_cap = self._parse_number(payload.get("market_cap_billion") or payload.get("marketCap") or payload.get("market_cap"))
                if market_cap is None:
                    market_cap = relation_metrics.get("market_cap_billion")
                pe_basic = self._parse_number(payload.get("pe_basic") or payload.get("PEBasic") or payload.get("pe") or payload.get("PE"))
                if pe_basic is None:
                    pe_basic = relation_metrics.get("pe_basic")
                peers.append(
                    {
                        "symbol": normalize_symbol(symbol),
                        "company": self._clean_peer_company_candidate(
                            payload.get("company") or payload.get("companyName") or payload.get("StockName") or payload.get("stockName") or payload.get("organName") or payload.get("name"),
                            symbol,
                        ),
                        "exchange": payload.get("exchange") or payload.get("market") or payload.get("marketCode"),
                        "industry": payload.get("industry") or payload.get("industryName"),
                        "close_price": close_price,
                        "change_1d_percent": self._parse_number(payload.get("change_1d_percent") or payload.get("changePercent") or payload.get("change1DPercent")),
                        "matched_volume": self._parse_number(payload.get("matched_volume") or payload.get("matchVolume") or payload.get("volume")),
                        "matched_value_billion": self._parse_number(payload.get("matched_value_billion") or payload.get("matchedValue") or payload.get("value")),
                        "fundamental_rating": payload.get("fundamental_rating") or payload.get("fundamentalRating") or payload.get("rating"),
                        "buy_sell_signal": payload.get("buy_sell_signal") or payload.get("buySellSignal") or payload.get("signal"),
                        "market_cap_billion": market_cap,
                        "eps_4q": self._parse_number(payload.get("eps_4q") or payload.get("eps4Q") or payload.get("eps")),
                        "pe_basic": pe_basic,
                        "macd": self._parse_number(payload.get("macd") or payload.get("MACD")),
                        "rsi_14": self._parse_number(payload.get("rsi_14") or payload.get("rsi14") or payload.get("RSI")),
                        "basic_score": self._parse_number(payload.get("basic_score") or payload.get("basicScore")),
                        "first_trading_date": payload.get("first_trading_date") or payload.get("firstTradingDate"),
                        "price": close_price,
                        "market_cap": market_cap,
                        "pe": pe_basic,
                        "pb": self._parse_number(payload.get("pb") or payload.get("PB")) or relation_metrics.get("pb"),
                        "roe": self._parse_number(payload.get("roe") or payload.get("ROE")) or relation_metrics.get("roe"),
                        **relation_metrics,
                        "source": self.source_name,
                        "source_url": source_url,
                        "same_industry_reason": "Xuất hiện trong dữ liệu so sánh cùng ngành của Vietstock Finance.",
                        "verified_row_evidence": "json",
                        "confidence": 0.78,
                    }
                )
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    peers.extend(self._extract_peers_from_json(value, source_url=source_url))
        return peers

    def _extract_industry_context(self, html_text: str, *, source_url: str) -> dict[str, Any]:
        text = self._clean_html_text(html_text)
        if not text:
            return {}
        normalized = self._normalize_text(text)
        industry: dict[str, Any] = {}
        sector_terms = [
            ("tai chinh", "Tài chính"),
            ("cong nghe thong tin", "Công nghệ thông tin"),
            ("vat lieu xay dung", "Vật liệu xây dựng"),
            ("thep", "Thép"),
            ("bat dong san", "Bất động sản"),
            ("ngan hang", "Ngân hàng"),
        ]
        for needle, label in sector_terms:
            if needle in normalized:
                if label in {"Tài chính", "Công nghệ thông tin", "Vật liệu xây dựng", "Bất động sản"}:
                    industry.setdefault("sector", label)
                elif label == "Ngân hàng":
                    industry.setdefault("industry", label)
                elif label == "Thép":
                    industry.setdefault("industry", label)
        if "to chuc tin dung" in normalized:
            industry.setdefault("industry_group", "Tổ chức tín dụng")
        heading = re.search(r"Doanh\s+nghiệp\s+trong\s+ngành\s+([^<\n\r|]+)", text, flags=re.IGNORECASE)
        if heading:
            clean_heading = re.sub(r"\s+", " ", heading.group(1)).strip(" :-–—|")
            if clean_heading and len(clean_heading) <= 80:
                industry.setdefault("industry", clean_heading)
        if not industry:
            return {}
        industry["source"] = self.source_name
        industry["source_url"] = source_url
        return industry

    def _symbol_from_symbol_company_cell(self, value: Any) -> str | None:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return None
        first = text.split(" ", 1)[0].strip(":-–—|")
        if self._looks_like_symbol(first):
            return normalize_symbol(first)
        return normalize_symbol(text) if self._looks_like_symbol(text) else None

    def _company_from_symbol_company_cell(self, value: Any, symbol: str) -> str | None:
        text = re.sub(r"\s+", " ", html_lib.unescape(str(value or ""))).strip()
        if not text:
            return None
        match = re.match(rf"^\s*{re.escape(symbol)}\s+(.+)$", text, flags=re.IGNORECASE)
        if not match:
            return None
        return self._clean_peer_company_candidate(match.group(1), symbol)

    def _relation_company_metrics(self, payload: dict[str, Any]) -> dict[str, Any]:
        columns = payload.get("Columns")
        values = payload.get("Values")
        if not isinstance(columns, list) or not isinstance(values, list):
            return {}
        metrics: dict[str, Any] = {}
        for column, raw_value in zip(columns, values):
            normalized = self._normalize_text(str(column or ""))
            value = self._parse_number(raw_value)
            if value is None:
                continue
            if "vhtt" in normalized or "von hoa" in normalized:
                market_cap = value / 1_000_000_000 if value > 10_000_000 else value
                metrics["market_cap_billion"] = round(market_cap, 2)
                metrics["market_cap"] = round(market_cap, 2)
            elif "stochrsi" in normalized or "stoch rsi" in normalized:
                metrics["stoch_rsi"] = value
            elif "trrsi14" in normalized or "rsi 14" in normalized:
                metrics["rsi_14"] = value
            elif "trmacd" in normalized or "macd" in normalized:
                metrics["macd"] = value
            elif "trmomentum10" in normalized or "mom" in normalized:
                metrics["momentum_1m"] = value
            elif "pe" in normalized and "p/e" in normalized:
                metrics["pe_basic"] = value
                metrics["pe"] = value
            elif "pb" in normalized or "p/b" in normalized:
                metrics["pb"] = value
            elif "roe" in normalized:
                metrics["roe"] = value
        signal_columns = [
            (str(column or ""), values[index])
            for index, column in enumerate(columns)
            if index < len(values) and "tin hieu mua ban" in self._normalize_text(str(column or ""))
        ]
        if signal_columns:
            signal = self._signal_label(signal_columns[0][1])
            if signal:
                metrics["buy_sell_signal"] = signal
        return metrics

    def _signal_label(self, value: Any) -> str | None:
        try:
            code = int(float(str(value).replace(",", ".")))
        except (TypeError, ValueError):
            return str(value).strip() or None
        return {1: "Bán mạnh", 2: "Bán", 3: "Trung tính", 4: "Bán", 5: "Bán mạnh", 6: "Mua", 7: "Mua mạnh"}.get(code)

    def _peer_failure_reason(self, debug_info: dict[str, Any]) -> str:
        tables = debug_info.get("tables_found") or len(debug_info.get("raw_rows") or [])
        headers = len(debug_info.get("headers_found") or [])
        grids = debug_info.get("grid_rows_found") or 0
        return f"page_loaded=true; tables_or_rows_found={tables}; headers_found={headers}; grid_rows_found={grids}; normalized_peers=0"

    def _parse_text_lines(self, html_text: str, *, source_url: str) -> list[dict[str, Any]]:
        """Legacy helper kept for tests/debug, not used for final peer extraction."""
        lines = []
        peers: list[dict[str, Any]] = []
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            symbol = parts[0]
            if not self._looks_like_symbol(symbol):
                continue
            nums = [self._parse_number(part) for part in parts[1:]]
            numeric = [value for value in nums if value is not None]
            peer: dict[str, Any] = {
                "symbol": normalize_symbol(symbol),
                "source": self.source_name,
                "source_url": source_url,
                "same_industry_reason": "Xuất hiện trong nội dung so sánh cùng ngành của Vietstock Finance.",
                "confidence": 0.65,
            }
            for key, value in zip(("price", "pe", "pb", "roe", "momentum_1m"), numeric):
                peer[key] = value
            peers.append(peer)
        return peers

    def _parse_stock_link_rows(self, html_text: str, *, source_url: str) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        if not html_text:
            return peers
        row_pattern = re.compile(r"(?is)<tr\b[^>]*>(.*?)</tr>")
        rows = row_pattern.findall(html_text)
        if not rows:
            rows = re.findall(r"(?is)<(?:div|li)\b[^>]*(?:row|item|stock|symbol|company|compare|industry)[^>]*>(.*?)</(?:div|li)>", html_text)
        for row_html in rows:
            peers.extend(self._parse_stock_links_from_fragment(row_html, source_url=source_url, require_row_context=True))
        return peers

    def _parse_stock_links_from_fragment(self, fragment: str, *, source_url: str, require_row_context: bool) -> list[dict[str, Any]]:
        peers: list[dict[str, Any]] = []
        if require_row_context and not self._has_peer_row_context(fragment):
            return peers
        for match in re.finditer(r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", fragment or "", flags=re.IGNORECASE | re.DOTALL):
            href = html_lib.unescape(match.group(1) or "")
            symbol = self._symbol_from_stock_href(href)
            if not symbol:
                continue
            link_text = self._clean_html_text(match.group(2))
            row_text = self._clean_html_text(fragment)
            company = self._company_from_link_text(symbol, link_text, row_text)
            peer = {
                "symbol": symbol,
                "company": company,
                "source": self.source_name,
                "source_url": source_url,
                "same_industry_reason": "Xuất hiện trong dòng dữ liệu cùng ngành của Vietstock Finance.",
                "verified_stock_link": href,
                "verified_row_evidence": "stock_link",
                "confidence": 0.65 if company else 0.55,
            }
            metrics = self._numeric_metrics_from_row_text(row_text)
            peer.update(metrics)
            peers.append({key: value for key, value in peer.items() if value not in (None, "")})
        return peers

    def _has_peer_row_context(self, fragment: str) -> bool:
        text = self._normalize_text(self._clean_html_text(fragment))
        markers = (
            "ma chung khoan",
            "doanh nghiep",
            "p/e",
            "p/b",
            "roe",
            "rsi",
            "tin hieu",
            "gia",
            "von hoa",
            "san",
        )
        return any(marker in text for marker in markers) or bool(self._symbol_from_stock_href(fragment))

    def _symbol_from_stock_href(self, href: str) -> str | None:
        match = re.search(r"(?:https?://finance\.vietstock\.vn)?/([A-Z][A-Z0-9]{2,5})(?:[/?#.-]|$)", href or "")
        if not match:
            return None
        symbol = normalize_symbol(match.group(1))
        return symbol if self._looks_like_symbol(symbol) else None

    def _company_from_link_text(self, symbol: str, link_text: str, row_text: str) -> str | None:
        clean_link = re.sub(r"\s+", " ", link_text or "").strip()
        if clean_link:
            clean_link = re.sub(rf"^\s*{re.escape(symbol)}\s*[-:|]?\s*", "", clean_link, flags=re.IGNORECASE).strip()
            company = self._clean_peer_company_candidate(clean_link, symbol)
            if company:
                return company
        return None

    def _clean_peer_company_candidate(self, value: Any, symbol: str | None = None) -> str | None:
        clean = re.sub(r"\s+", " ", html_lib.unescape(str(value or ""))).strip(" -–—|:")
        if not clean:
            return None
        if symbol:
            clean = re.sub(rf"^\s*{re.escape(str(symbol))}\s*[-:|]?\s*", "", clean, flags=re.IGNORECASE).strip(" -–—|:")
        if not clean or self._looks_like_symbol(clean):
            return None
        normalized = self._normalize_text(clean)
        forbidden_terms = (
            "bang gia",
            "dang nhap",
            "danh muc",
            "tin hieu mua ban",
            "xep hang co ban",
            "ban manh",
            "mua manh",
        )
        if any(term in normalized for term in forbidden_terms):
            return None
        numeric_tokens = re.findall(r"-?\d[\d,.]*", clean)
        if len(numeric_tokens) >= 3:
            return None
        if len(clean) < 4 or len(clean) > 140:
            return None
        if re.match(r"^\d+\s+[A-Z0-9]{2,5}\b", clean):
            return None
        return clean

    def _debug_table_snapshot(self, tables: list[list[list[str]]]) -> dict[str, Any]:
        headers_found: list[dict[str, Any]] = []
        raw_rows: list[dict[str, Any]] = []
        for table_index, table in enumerate(tables[:8]):
            for row_index, row in enumerate(table[:80]):
                mapped = self._header_map(row)
                if mapped:
                    headers_found.append({"table_index": table_index, "row_index": row_index, "headers": row, "mapped": mapped})
                if row:
                    raw_rows.append({"table_index": table_index, "row_index": row_index, "cells": row, "text": " ".join(row)})
        return {
            "tables_found": len(tables),
            "grid_rows_found": 0,
            "headers_found": headers_found[:20],
            "raw_rows": raw_rows[:200],
            "raw_rows_sample": raw_rows[:20],
            "rejected_rows": [],
            "normalized_peers_count": 0,
            "failure_reason": "",
        }

    def _numeric_metrics_from_row_text(self, row_text: str) -> dict[str, Any]:
        normalized = self._normalize_text(row_text)
        values = [value for value in (self._parse_number(part) for part in re.findall(r"\(?-?\d[\d,.]*%?\)?", row_text or "")) if value is not None]
        metrics: dict[str, Any] = {}
        if "p/e" in normalized or " pe " in f" {normalized} ":
            if values:
                metrics["pe"] = values[0]
        if "p/b" in normalized and len(values) >= 2:
            metrics["pb"] = values[1]
        if "roe" in normalized and values:
            metrics["roe"] = values[-1]
        return metrics

    def _finalize_peers(self, peers: list[dict[str, Any]], *, symbol: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        by_symbol: dict[str, dict[str, Any]] = {}
        for peer in peers:
            peer_symbol = normalize_symbol(peer.get("symbol") or peer.get("ticker"))
            if not peer_symbol or peer_symbol == symbol:
                continue
            peer["symbol"] = peer_symbol
            if not self._is_valid_peer_row(peer):
                continue
            if not (peer.get("source") or peer.get("source_url")):
                continue
            if peer_symbol in by_symbol:
                by_symbol[peer_symbol] = self._merge_peer_rows(by_symbol[peer_symbol], peer)
                continue
            useful = self._useful_metric_keys(peer)
            if len(useful) < 2:
                peer.setdefault("quantitative_label", "Cần bổ sung: giá, P/E/PB/ROE")
            by_symbol[peer_symbol] = peer
        result = list(by_symbol.values())[: self.settings.vietstock_peer_max_items]
        for peer in result:
            useful = self._useful_metric_keys(peer)
            if len(useful) >= 2:
                peer.pop("quantitative_label", None)
                peer["confidence"] = max(float(peer.get("confidence") or 0), 0.75)
        return result

    def _merge_peer_rows(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in incoming.items():
            if value in (None, ""):
                continue
            if key not in merged or merged.get(key) in (None, ""):
                merged[key] = value
            elif key in {"verified_row_evidence"} and value not in str(merged.get(key)):
                merged[key] = f"{merged[key]},{value}"
        return merged

    def _is_valid_peer_row(self, peer: dict[str, Any]) -> bool:
        symbol = normalize_symbol(peer.get("symbol") or peer.get("ticker"))
        if not self._looks_like_symbol(symbol):
            return False
        if not peer.get("source_url"):
            return False
        if not peer.get("verified_row_evidence"):
            return False
        useful = self._useful_metric_keys(peer)
        if len(useful) >= 2 and bool(peer.get("company") or peer.get("verified_row_evidence") in {"table", "json"}):
            return True
        return bool(peer.get("company")) and str(peer.get("verified_row_evidence")) in {"stock_link", "table", "json"}

    def _peer_status(self, peers: list[dict[str, Any]]) -> str:
        if not peers:
            return "insufficient"
        for peer in peers:
            useful = self._useful_metric_keys(peer)
            if peer.get("company") and len(useful) >= 2:
                return "success"
        return "partial"

    def _useful_metric_keys(self, peer: dict[str, Any]) -> list[str]:
        fields = (
            "price",
            "close_price",
            "change_1d_percent",
            "matched_volume",
            "matched_value_billion",
            "market_cap",
            "market_cap_billion",
            "eps_4q",
            "pe",
            "pe_basic",
            "pb",
            "roe",
            "revenue",
            "profit_after_tax",
            "net_margin",
            "momentum_1m",
            "liquidity",
            "macd",
            "rsi_14",
            "basic_score",
        )
        return [
            key
            for key in fields
            if isinstance(peer.get(key), (int, float)) and not isinstance(peer.get(key), bool)
        ]

    def _looks_like_symbol(self, value: Any) -> bool:
        text = normalize_symbol(str(value or ""))
        forbidden = {
            "SPOT",
            "TIN",
            "DOANH",
            "GIAO",
            "THANH",
            "TOP",
            "QUY",
            "THEO",
            "DANH",
            "VIMO",
            "NGANH",
            "DOANHNGHIEP",
            "TAICHINH",
            "VNINDEX",
            "VN30",
            "HOSE",
            "HNX",
            "UPCOM",
            "LOGIN",
            "SEARCH",
            "MENU",
        }
        return bool(re.fullmatch(r"[A-Z][A-Z0-9]{2,5}", text)) and text not in forbidden

    def _clean_html_text(self, html_text: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text or "")
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()

    def _parse_number(self, value: Any) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = self._normalize_text(text)
        if normalized in {"-", "--", "n/a", "na", "none", "chua co du lieu"}:
            return None
        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative = True
            text = text[1:-1]
        text = re.sub(r"[^\d,.\-]", "", text)
        if not text or text in {"-", ".", ","}:
            return None
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            parts = text.split(",")
            if len(parts[-1]) == 3 and all(part.isdigit() for part in parts if part):
                text = "".join(parts)
            else:
                text = ".".join(parts)
        try:
            number = float(text)
        except ValueError:
            return None
        return -number if negative and number > 0 else number

    def _extract_text_lines(self, html_text: str) -> list[str]:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "\n", html_text or "")
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</(div|tr|td|th|p|li|span|section|article|h[1-6])>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_lib.unescape(text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return [line for line in lines if line]

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

    async def _fetch_with_cache(self, url: str, cache_kind: str) -> str:
        cached = self._read_cache(url, cache_kind=cache_kind)
        if cached is not None:
            return cached
        headers = {"User-Agent": self.settings.research_user_agent}
        if hasattr(self.http_client, "get_text"):
            text = await self.http_client.get_text(url, headers=headers)
        else:
            response = await self.http_client.get(url, headers=headers)
            text = response.text
        self._write_cache(url, text, cache_kind=cache_kind)
        return text

    def _cache_path(self, url: str, cache_kind: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"vietstock_peer_{cache_kind}_{digest}.json"

    def _read_cache(self, url: str, cache_kind: str) -> str | None:
        path = self._cache_path(url, cache_kind=cache_kind)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_at = float(payload.get("cached_at") or 0)
            if time.time() - cached_at > self.settings.vietstock_peer_cache_ttl_seconds:
                return None
            return str(payload.get("text") or "")
        except Exception:
            return None

    def _write_cache(self, url: str, text: str, cache_kind: str) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(url, cache_kind=cache_kind).write_text(
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
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_rendered.html").write_text(html_text, encoding="utf-8")
        except Exception:
            return

    def _save_raw_debug(self, symbol: str, html_text: str) -> None:
        if not (self.settings.external_data_debug_save_rendered_html or self.settings.vietstock_debug_save_rendered_html):
            return
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_raw.html").write_text(html_text or "", encoding="utf-8")
        except Exception:
            return

    def _save_request_debug(self, symbol: str, source_url: str, result: dict[str, Any], *, http_status: str, render_status: str) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        debug = result.get("debug") if isinstance(result.get("debug"), dict) else {}
        payload = {
            "url": source_url,
            "http_status": http_status,
            "used_playwright": "render" in render_status,
            "render_status": render_status,
            "tab_selected": debug.get("tab_selected") or self.settings.vietstock_peer_default_tab,
            "tables_found": debug.get("tables_found") or 0,
            "grid_rows_found": debug.get("grid_rows_found") or 0,
            "headers_found": debug.get("headers_found") or [],
            "normalized_peers_count": len(result.get("peers") or []),
            "failure_reason": debug.get("failure_reason"),
            "status": result.get("status"),
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_request.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_extraction_debug(
        self,
        symbol: str,
        source_url: str,
        result: dict[str, Any],
        *,
        render_status: str,
        html_text: str,
    ) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        peers = result.get("peers") if isinstance(result.get("peers"), list) else []
        debug = result.get("debug") if isinstance(result.get("debug"), dict) else {}
        payload = {
            "url": source_url,
            "source_url": source_url,
            "render_status": render_status,
            "used_playwright": "render" in render_status,
            "wait_strategy_used": self._safe_wait_until(self.settings.vietstock_peer_browser_wait_until),
            "tab_selected": debug.get("tab_selected") or self.settings.vietstock_peer_default_tab,
            "tables_found": debug.get("tables_found") or len(re.findall(r"(?is)<table\b", html_text or "")),
            "grid_rows_found": debug.get("grid_rows_found") or 0,
            "headers_found": debug.get("headers_found") or [],
            "raw_rows": debug.get("raw_rows") or [],
            "raw_rows_sample": debug.get("raw_rows_sample") or (debug.get("raw_rows") or [])[:20],
            "normalized_rows": debug.get("normalized_rows") or peers,
            "normalized_peers_count": len(peers),
            "rejected_rows": debug.get("rejected_rows") or [],
            "peer_row_count": len(peers),
            "rejected_peer_tokens": self._rejected_tokens_from_text(html_text),
            "final_valid_peers": peers,
            "status": result.get("status"),
            "failure_reason": debug.get("failure_reason"),
            "warnings": result.get("warnings") or [],
            "technical_warnings": result.get("technical_warnings") or [],
        }
        tables_payload = {
            "url": source_url,
            "used_playwright": payload["used_playwright"],
            "tables_found": payload["tables_found"],
            "grid_rows_found": payload["grid_rows_found"],
            "headers_found": payload["headers_found"],
            "raw_rows_sample": payload["raw_rows_sample"],
            "normalized_peers_count": payload["normalized_peers_count"],
            "rejected_rows": payload["rejected_rows"],
            "failure_reason": payload["failure_reason"],
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_tables.json").write_text(
                json.dumps(tables_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_extraction.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_raw_rows.json").write_text(
                json.dumps(
                    {
                        "source_url": source_url,
                        "tab_selected": payload["tab_selected"],
                        "headers_found": payload["headers_found"],
                        "raw_rows": payload["raw_rows"],
                        "rejected_rows": payload["rejected_rows"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_peer_normalized.json").write_text(
                json.dumps(
                    {
                        "source_url": source_url,
                        "tab_selected": payload["tab_selected"],
                        "normalized_rows": payload["normalized_rows"],
                        "final_valid_peers": peers,
                        "status": result.get("status"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            return

    def _rejected_tokens_from_text(self, html_text: str) -> list[dict[str, str]]:
        text = self._clean_html_text(html_text)
        candidates = sorted(set(re.findall(r"\b[A-ZĐ]{3,10}\b", text or "")))
        rejected = []
        for token in candidates[:200]:
            normalized = normalize_symbol(token)
            if not self._looks_like_symbol(normalized):
                rejected.append({"token": token, "reason": "Không có bằng chứng dòng peer hợp lệ hoặc là từ khóa/navigation."})
        return rejected

    def _result(
        self,
        source_url: str,
        peers: list[dict[str, Any]],
        warnings: list[str],
        technical_warnings: list[str],
        status: str,
        industry: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "source_url": source_url,
            "fetched_at": now_iso(),
            "peers": peers,
            "industry": industry or {},
            "warnings": _dedupe_preserve_order(warnings),
            "technical_warnings": _dedupe_preserve_order(technical_warnings),
            "status": status,
            "debug": debug or {},
        }

    def _as_list(self, value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return [str(value)]

    def _safe_wait_until(self, value: str | None) -> str:
        wait_until = (value or "domcontentloaded").strip().lower()
        if wait_until == "networkidle":
            return "domcontentloaded"
        if wait_until not in {"commit", "domcontentloaded", "load"}:
            return "domcontentloaded"
        return wait_until
