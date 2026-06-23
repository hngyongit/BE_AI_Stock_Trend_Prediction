from __future__ import annotations

import hashlib
import html as html_lib
import importlib
import json
import logging
import re
import time
import unicodedata
import asyncio
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings, get_settings
from analyse.services.stock_data_service import FINANCIAL_METRIC_FIELDS
from analyse.services.stock_data_service import StockDataService
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


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


class PlaywrightVietstockRenderer:
    """Render Vietstock Finance pages with a real browser when static HTML is incomplete."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_rendered_html(self, url: str) -> tuple[str | None, list[str]]:
        ensure_windows_proactor_event_loop_policy()
        return await run_in_windows_proactor_thread(lambda: self._fetch_rendered_html_direct(url))

    async def _fetch_rendered_html_direct(self, url: str) -> tuple[str | None, list[str]]:
        warnings: list[str] = []
        try:
            playwright_api = importlib.import_module("playwright.async_api")
        except ImportError:
            return (
                None,
                [
                    "Playwright chưa được cài đặt hoặc Chromium chưa sẵn sàng; "
                    "cần chạy pip install playwright và python -m playwright install chromium."
                ],
            )

        async_playwright = playwright_api.async_playwright
        captured_payloads: list[str] = []
        pending_tasks: list[asyncio.Task[Any]] = []
        browser = None
        context = None
        page = None
        label = "playwright:vietstock-bctc"
        response_handler = None
        debug_error: BaseException | None = None
        debug_phase = "unknown"
        try:
            async with async_playwright() as playwright:
                logger.info("[%s] launch browser", label)
                browser = await playwright.chromium.launch(
                    headless=self.settings.effective_vietstock_financial_browser_headless
                )
                context = await browser.new_context(
                    viewport={
                        "width": self.settings.effective_vietstock_financial_browser_viewport_width,
                        "height": self.settings.effective_vietstock_financial_browser_viewport_height,
                    },
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
                        markers = (
                            "doanh thu",
                            "loi nhuan",
                            "lợi nhuận",
                            "thu nhập lãi",
                            "netinterest",
                            "profit",
                            "financial",
                            "balance",
                            "quarter",
                            "period",
                        )
                        if any(marker in normalized for marker in markers):
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
                timeout_ms = max(self.settings.effective_vietstock_financial_timeout_ms, 60000)
                wait_until = self._safe_wait_until(self.settings.effective_vietstock_financial_browser_wait_until)
                logger.info("[%s] goto URL", label)
                warnings.extend(await self._goto_safely(page, url, wait_until=wait_until, timeout_ms=timeout_ms))
                warnings.extend(await self._select_financial_controls(page))
                warnings.extend(await self._wait_for_financial_content(page))
                if self.settings.effective_vietstock_financial_browser_extra_wait_ms > 0:
                    await page.wait_for_timeout(
                        self.settings.effective_vietstock_financial_browser_extra_wait_ms
                    )
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
                return html_text, _dedupe_preserve_order(warnings)
        except asyncio.CancelledError as exc:
            debug_error = exc
            debug_phase = "cancelled"
            logger.warning("[%s] Request cancelled; cleaning up Playwright", label)
            await cancel_pending_tasks_safely(pending_tasks, label=label)
            raise
        except TargetClosedError as exc:  # pragma: no cover - exact browser errors depend on host
            debug_error = exc
            debug_phase = "goto/extract"
            message = safe_playwright_error_message(exc)
            logger.warning("[%s] Playwright target closed: %s", label, message)
            return None, [f"Playwright rendering failed: TargetClosedError: {message}"]
        except PlaywrightTimeoutError as exc:  # pragma: no cover - exact browser errors depend on host
            debug_error = exc
            debug_phase = "goto/extract"
            message = safe_playwright_error_message(exc)
            logger.warning("[%s] Playwright timeout: %s", label, message)
            return None, [f"Playwright rendering failed: TimeoutError: {message}"]
        except Exception as exc:  # pragma: no cover - exact browser errors depend on host
            debug_error = exc
            debug_phase = "goto/extract"
            if is_target_closed_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright target closed: %s", label, message)
                return None, [f"Playwright rendering failed: TargetClosedError: {message}"]
            if is_playwright_timeout_error(exc):
                message = safe_playwright_error_message(exc)
                logger.warning("[%s] Playwright timeout: %s", label, message)
                return None, [f"Playwright rendering failed: TimeoutError: {message}"]
            logger.warning("[%s] Playwright crawler failed safely: %s", label, exc, exc_info=True)
            return (
                None,
                [
                    "Playwright rendering failed: "
                    f"{exc.__class__.__name__}: {self._safe_error_message(exc)}"
                ],
            )
        finally:
            if response_handler is not None:
                remove_playwright_listener_safely(page, "response", response_handler, label=label)
            logger.info("[%s] pending tasks count=%s", label, len([task for task in pending_tasks if not task.done()]))
            await cancel_pending_tasks_safely(pending_tasks, label=label)
            await close_playwright_objects_safely(page=page, context=context, browser=browser, label=label)
            if debug_error is not None:
                save_playwright_error_debug(
                    self.settings,
                    source="Vietstock BCTC",
                    url=url,
                    slug="vietstock_bctc",
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

    async def _goto_safely(self, page: Any, url: str, *, wait_until: str, timeout_ms: int) -> list[str]:
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return [f"Vietstock browser wait_until={wait_until}."]
        except Exception as exc:
            message = self._safe_error_message(exc)
            warning = f"Vietstock browser goto warning: {exc.__class__.__name__}: {message}"
            try:
                content = await page.content()
                if content and len(content) > 500:
                    return [warning, "Vietstock page content was available after goto warning; parser continued."]
            except Exception:
                pass
            raise

    async def _select_financial_controls(self, page: Any) -> list[str]:
        warnings: list[str] = []
        for text in ("Quý", "Tỷ đồng"):
            clicked = await self._try_click_text(page, text)
            if clicked:
                warnings.append(f"Đã chọn chế độ {text} nếu điều khiển tồn tại.")
        return warnings

    async def _try_click_text(self, page: Any, text: str) -> bool:
        candidates = [
            f"text={text}",
            f"button:has-text('{text}')",
            f"a:has-text('{text}')",
            f"label:has-text('{text}')",
        ]
        for selector in candidates:
            try:
                locator = page.locator(selector).first()
                if await locator.count() <= 0:
                    continue
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=1500)
                    await page.wait_for_timeout(500)
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_financial_content(self, page: Any) -> list[str]:
        selector = (self.settings.effective_vietstock_financial_browser_wait_selector or "").strip()
        selectors = [selector] if selector else [
            "table",
            "text=Thu nhập lãi thuần",
            "text=Tổng lợi nhuận trước thuế",
            "text=Tiền gửi của khách hàng",
            "text=Doanh thu thuần",
            "text=Lợi nhuận gộp",
            "text=Doanh thu thuần",
            "text=Lợi nhuận sau thuế",
            "text=Tổng cộng tài sản",
            "text=Báo cáo tài chính",
            "text=Cho vay khách hàng",
            "[class*=financial]",
            "[id*=financial]",
            "[class*=finance]",
            "[id*=finance]",
        ]
        timeout = min(max(self.settings.effective_vietstock_financial_timeout_ms // 4, 2000), 7000)
        for candidate in selectors:
            try:
                await page.wait_for_selector(candidate, timeout=timeout)
                return []
            except Exception:
                continue
        return ["Không xác nhận được selector bảng tài chính sau khi render Vietstock."]

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        if len(message) > 180:
            message = message[:177].rstrip() + "..."
        return message or "không có thông điệp chi tiết"


class VietstockFinancialAdapter:
    source_name = "Vietstock Finance"

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: HttpClient | None = None,
        browser_renderer: PlaywrightVietstockRenderer | Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client or HttpClient(
            timeout_ms=self.settings.effective_vietstock_financial_timeout_ms
        )
        self.browser_renderer = browser_renderer or PlaywrightVietstockRenderer(self.settings)
        self.cache_dir = Path(self.settings.research_cache_dir)

    async def fetch(self, symbol: str) -> dict[str, Any]:
        clean_symbol = normalize_symbol(symbol)
        source_url = self.settings.effective_vietstock_financial_url_template.format(symbol=clean_symbol)
        if not self.settings.effective_enable_vietstock_financial_fallback:
            return self._result(
                source_url=source_url,
                periods=[],
                warnings=["Fallback BCTC Vietstock đang tắt theo cấu hình."],
                technical_warnings=[],
                status="disabled",
            )

        warnings: list[str] = []
        technical_warnings: list[str] = []
        try:
            html_text = await self._fetch_with_cache(source_url, cache_kind="static")
        except Exception as exc:
            warnings.append(
                f"Không tải được Vietstock Finance bằng HTTP: {exc.__class__.__name__}"
            )
            technical_warnings.append(
                f"Vietstock static HTTP fetch failed: {exc.__class__.__name__}: {exc}"
            )
            return self._result(
                source_url=source_url,
                periods=[],
                warnings=warnings,
                technical_warnings=technical_warnings,
                status="failed",
            )

        parsed = self.parse_html(html_text, source_url=source_url)
        if parsed.get("periods"):
            self._save_extraction_debug(clean_symbol, source_url, parsed, render_status="static_success")
            return parsed

        warnings.extend(self._as_list(parsed.get("warnings")))
        technical_warnings.extend(self._as_list(parsed.get("technical_warnings")))
        warnings.append("Không tìm thấy bảng tài chính trong HTML tĩnh, chuyển sang render bằng trình duyệt.")

        if not self.settings.effective_vietstock_financial_use_browser_fallback:
            warnings.append("Browser fallback Vietstock đang tắt theo cấu hình.")
            return self._result(
                source_url=source_url,
                periods=[],
                warnings=_dedupe_preserve_order(warnings),
                technical_warnings=_dedupe_preserve_order(technical_warnings),
                status="partial",
            )

        rendered_html = self._read_cache(source_url, cache_kind="rendered")
        if rendered_html is None:
            rendered_html, browser_warnings = await self.browser_renderer.fetch_rendered_html(
                source_url
            )
            warnings.extend(browser_warnings)
            technical_warnings.extend(browser_warnings)
            if rendered_html:
                self._write_cache(source_url, rendered_html, cache_kind="rendered")
                self._save_rendered_debug(clean_symbol, rendered_html)

        if not rendered_html:
            result = self._result(
                source_url=source_url,
                periods=[],
                warnings=_dedupe_preserve_order(warnings),
                technical_warnings=_dedupe_preserve_order(technical_warnings),
                status="failed",
            )
            self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_failed")
            return result

        rendered_parsed = self.parse_html(rendered_html, source_url=source_url)
        rendered_periods = rendered_parsed.get("periods") or []
        warnings.extend(self._as_list(rendered_parsed.get("warnings")))
        technical_warnings.extend(self._as_list(rendered_parsed.get("technical_warnings")))
        if rendered_periods:
            result = self._result(
                source_url=source_url,
                periods=rendered_periods,
                warnings=_dedupe_preserve_order(warnings),
                technical_warnings=_dedupe_preserve_order(technical_warnings),
                status="success",
            )
            self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_success")
            return result

        warnings.append("Không tìm thấy bảng tài chính trong nội dung đã render từ Vietstock Finance.")
        result = self._result(
            source_url=source_url,
            periods=[],
            warnings=_dedupe_preserve_order(warnings),
            technical_warnings=_dedupe_preserve_order(technical_warnings),
            status="partial",
        )
        self._save_extraction_debug(clean_symbol, source_url, result, render_status="render_partial")
        return result

    def parse_html(self, html_text: str, source_url: str) -> dict[str, Any]:
        parser = _TableParser()
        parser.feed(html_text or "")
        periods_by_label: dict[str, dict[str, Any]] = {}
        unit = self._detect_unit(html_text or "")
        for table in parser.tables:
            self._parse_table(table, periods_by_label)
        self._parse_json_payloads(html_text or "", periods_by_label)

        if not periods_by_label:
            self._parse_text_grid(html_text or "", periods_by_label)

        detected_periods = StockDataService.sanitize_financial_periods(self._finalize_periods(periods_by_label))
        periods = [period for period in detected_periods if self._is_valid_financial_period(period)]
        validation_warnings = StockDataService.financial_suspicious_notes(detected_periods)
        warnings: list[str] = []
        warnings.extend(validation_warnings)
        if not periods:
            if detected_periods:
                warnings.append("Chỉ nhận diện được kỳ báo cáo nhưng chưa trích xuất đủ số liệu tài chính từ Vietstock Finance.")
            else:
                warnings.append("Không tìm thấy bảng tài chính trong HTML Vietstock Finance.")
        return self._result(
            source_url=source_url,
            periods=periods,
            warnings=warnings,
            technical_warnings=[],
            status="success" if periods else "partial",
            unit=unit,
        )

    def _parse_table(
        self,
        table: list[list[str]],
        periods_by_label: dict[str, dict[str, Any]],
    ) -> None:
        period_columns: list[tuple[int, dict[str, Any]]] = []
        for row in table[:8]:
            period_columns = self._find_period_columns(row)
            if len(period_columns) >= 1:
                break
        if not period_columns:
            return
        if any(meta.get("quarter") is not None for _, meta in period_columns):
            period_columns = [
                (index, meta) for index, meta in period_columns if meta.get("quarter") is not None
            ]
        if not period_columns:
            return

        period_indexes = {index for index, _ in period_columns}
        for row in table:
            if len(row) < 2:
                continue
            field = None
            for index, cell in enumerate(row):
                if index in period_indexes:
                    continue
                field = self._map_label_to_field(cell)
                if field:
                    break
            if not field:
                continue
            for index, meta in period_columns:
                if index >= len(row):
                    continue
                period_key = meta["period"]
                periods_by_label.setdefault(period_key, dict(meta))
                periods_by_label[period_key][field] = self._parse_number(row[index])

    def _parse_json_payloads(self, html_text: str, periods_by_label: dict[str, dict[str, Any]]) -> None:
        for match in re.finditer(
            r'<script[^>]+data-vietstock-financial-xhr[^>]*>(.*?)</script>',
            html_text or "",
            flags=re.IGNORECASE | re.DOTALL,
        ):
            payload = html_lib.unescape(match.group(1) or "")
            try:
                data = json.loads(payload)
            except Exception:
                continue
            self._walk_json_payload(data, periods_by_label)

    def _walk_json_payload(self, value: Any, periods_by_label: dict[str, dict[str, Any]]) -> None:
        if isinstance(value, list):
            for item in value:
                self._walk_json_payload(item, periods_by_label)
            return
        if not isinstance(value, dict):
            return

        self._json_record_to_period(value, periods_by_label)
        for item in value.values():
            if isinstance(item, (dict, list)):
                self._walk_json_payload(item, periods_by_label)

    def _json_record_to_period(self, record: dict[str, Any], periods_by_label: dict[str, dict[str, Any]]) -> None:
        label = self._first_text(
            record,
            "label",
            "name",
            "itemName",
            "criteriaName",
            "normName",
            "financeName",
            "indicatorName",
            "title",
            "rowName",
            "displayName",
        )
        field = self._map_label_to_field(label or "") if label else None
        if field:
            for key, value in record.items():
                meta = self._parse_period(key)
                if meta and self._parse_number(value) is not None:
                    periods_by_label.setdefault(meta["period"], dict(meta))
                    periods_by_label[meta["period"]][field] = self._parse_number(value)

        period_text = self._first_text(record, "period", "periodName", "reportPeriod", "termName", "reportTermName", "quarterName")
        meta = self._parse_period(period_text or "")
        if not meta:
            year = self._parse_int(record.get("year") or record.get("reportYear"))
            quarter = self._parse_int(record.get("quarter") or record.get("reportQuarter"))
            if year:
                meta = {"period": f"Q{quarter}/{year}" if quarter else str(year), "year": year, "quarter": quarter}
        if meta:
            periods_by_label.setdefault(meta["period"], dict(meta))
            if field:
                numeric_value = self._first_numeric(record, "value", "amount", "val", "data", "number", "currentValue")
                if numeric_value is not None:
                    periods_by_label[meta["period"]][field] = numeric_value
            for key, value in record.items():
                mapped_key = self._map_json_key_to_field(key)
                if mapped_key:
                    parsed = self._parse_number(value)
                    if parsed is not None:
                        periods_by_label[meta["period"]][mapped_key] = parsed

    def _map_json_key_to_field(self, key: Any) -> str | None:
        normalized = self._normalize_text(str(key or ""))
        compact = normalized.replace(" ", "").replace("_", "").replace("-", "")
        mapping = {
            "revenue": "revenue",
            "netrevenue": "revenue",
            "grossprofit": "gross_profit",
            "operatingprofit": "operating_profit",
            "profitbeforetax": "profit_before_tax",
            "profitaftertax": "profit_after_tax",
            "parentprofit": "parent_profit",
            "eps": "eps",
            "totalassets": "total_assets",
            "totalliabilities": "total_liabilities",
            "equity": "equity",
            "cash": "cash",
            "inventory": "inventory",
            "netinterestincome": "net_interest_income",
            "interestincome": "interest_income",
            "interestexpense": "interest_expense",
            "netfeeincome": "net_fee_income",
            "preprovisionoperatingprofit": "pre_provision_operating_profit",
            "creditprovisionexpense": "credit_provision_expense",
            "customerloans": "customer_loans",
            "customerdeposits": "customer_deposits",
            "nplratio": "npl_ratio",
            "nim": "nim",
            "casa": "casa_ratio",
            "roe": "roe",
            "roa": "roa",
            "pe": "pe",
            "pb": "pb",
            "bvps": "bvps",
        }
        return mapping.get(compact) or self._map_label_to_field(str(key or ""))

    def _first_text(self, data: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _first_numeric(self, data: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            parsed = self._parse_number(data.get(key))
            if parsed is not None:
                return parsed
        return None

    def _parse_int(self, value: Any) -> int | None:
        parsed = self._parse_number(value)
        if parsed is None:
            return None
        return int(parsed)

    def _parse_text_grid(
        self,
        html_text: str,
        periods_by_label: dict[str, dict[str, Any]],
    ) -> None:
        lines = self._extract_text_lines(html_text)
        period_meta = self._find_periods_in_lines(lines)
        if not period_meta:
            return
        for meta in period_meta:
            periods_by_label.setdefault(meta["period"], dict(meta))

        for line in lines:
            field = self._map_label_to_field(line)
            if not field:
                continue
            values = self._extract_numeric_values(line)
            if len(values) < 1:
                continue
            for index, value in enumerate(values[: len(period_meta)]):
                periods_by_label[period_meta[index]["period"]][field] = value

        self._parse_fragmented_text_grid(lines, period_meta, periods_by_label)

    def _parse_fragmented_text_grid(
        self,
        lines: list[str],
        period_meta: list[dict[str, Any]],
        periods_by_label: dict[str, dict[str, Any]],
    ) -> None:
        for index, line in enumerate(lines):
            field = self._map_label_to_field(line)
            if not field:
                continue
            values = self._extract_numeric_values(line)
            cursor = index + 1
            while len(values) < len(period_meta) and cursor < len(lines):
                next_line = lines[cursor]
                if cursor != index + 1 and self._map_label_to_field(next_line):
                    break
                if self._parse_period(next_line):
                    cursor += 1
                    continue
                extracted = self._extract_numeric_values(next_line)
                if extracted:
                    values.extend(extracted)
                elif self._map_label_to_field(next_line):
                    break
                cursor += 1
            for value_index, value in enumerate(values[: len(period_meta)]):
                periods_by_label[period_meta[value_index]["period"]][field] = value

    def _find_period_columns(self, row: list[str]) -> list[tuple[int, dict[str, Any]]]:
        columns: list[tuple[int, dict[str, Any]]] = []
        for index, cell in enumerate(row):
            parsed = self._parse_period(cell)
            if parsed:
                columns.append((index, parsed))
        return columns

    def _find_periods_in_lines(self, lines: list[str]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        periods: list[dict[str, Any]] = []
        for line in lines:
            candidates = re.findall(
                r"(?:Q[1-4]\s*/\s*20\d{2}|Quý\s*[1-4]\s*/\s*20\d{2}|20\d{2}\s*Q[1-4]|\b20\d{2}\b)",
                line,
                flags=re.IGNORECASE,
            )
            for candidate in candidates:
                parsed = self._parse_period(candidate)
                if parsed and parsed["period"] not in seen:
                    seen.add(parsed["period"])
                    periods.append(parsed)
        return self._finalize_period_meta(periods)

    def _parse_period(self, value: Any) -> dict[str, Any] | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = self._normalize_text(text)
        match = re.search(r"\bq\s*([1-4])\s*/?\s*(20\d{2})\b", normalized)
        if not match:
            match = re.search(r"\bquy\s*([1-4])\s*/?\s*(20\d{2})\b", normalized)
        if not match:
            match = re.search(r"\b(20\d{2})\s*q\s*([1-4])\b", normalized)
            if match:
                year = int(match.group(1))
                quarter = int(match.group(2))
                return {"period": f"Q{quarter}/{year}", "year": year, "quarter": quarter}
        if match:
            quarter = int(match.group(1))
            year = int(match.group(2))
            return {"period": f"Q{quarter}/{year}", "year": year, "quarter": quarter}
        if re.fullmatch(r"20\d{2}", normalized):
            year = int(normalized)
            return {"period": str(year), "year": year, "quarter": None}
        return None

    def _finalize_periods(
        self, periods_by_label: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return self._finalize_period_meta(list(periods_by_label.values()))

    def _finalize_period_meta(self, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if any(period.get("quarter") is not None for period in periods):
            periods = [period for period in periods if period.get("quarter") is not None]
        periods.sort(key=lambda item: (item.get("year") or 0, item.get("quarter") or 0), reverse=True)
        return periods[: self.settings.effective_vietstock_financial_max_periods]

    def _map_label_to_field(self, label: str) -> str | None:
        normalized = self._normalize_text(label)
        if not normalized:
            return None
        ratio_context = any(token in normalized for token in ("ty suat", "ty so", "chi so", "roa", "roaa", "roe", "roea", "p/e", "p/b"))
        if ratio_context:
            if "no vay tren von chu so huu" in normalized:
                return "debt_to_equity"
            if "no tren tong tai san" in normalized:
                return "debt_to_assets"
            if "gia thi truong tren thu nhap" in normalized or "p/e" in normalized:
                return "pe"
            if "gia thi truong tren gia tri so sach" in normalized or "p/b" in normalized:
                return "pb"
            if "tong tai san" in normalized and ("sinh loi" in normalized or "loi nhuan" in normalized or "roaa" in normalized or "roa" in normalized):
                return "roa"
            if "von chu so huu" in normalized and ("sinh loi" in normalized or "loi nhuan" in normalized or "roea" in normalized or "roe" in normalized):
                return "roe"
            if normalized in {"roaa", "roa"}:
                return "roa"
            if normalized in {"roea", "roe"}:
                return "roe"
        mapping: list[tuple[str, str]] = [
            ("thu nhap tren moi co phan cua 4 quy gan nhat", "eps_ttm"),
            ("gia tri so sach cua co phieu", "bvps"),
            ("chi so gia thi truong tren thu nhap", "pe"),
            ("p/e", "pe"),
            ("chi so gia thi truong tren gia tri so sach", "pb"),
            ("p/b", "pb"),
            ("ty suat loi nhuan gop bien", "gross_margin"),
            ("ty suat sinh loi tren doanh thu thuan", "net_margin"),
            ("ty suat loi nhuan tren von chu so huu binh quan", "roe"),
            ("ty suat sinh loi tren von chu so huu binh quan", "roe"),
            ("roea", "roe"),
            ("ty suat loi nhuan tren tong tai san binh quan", "roa"),
            ("ty suat sinh loi tren tong tai san binh quan", "roa"),
            ("roaa", "roa"),
            ("ty so thanh toan hien hanh", "current_ratio"),
            ("kha nang thanh toan lai vay", "interest_coverage"),
            ("ty so no tren tong tai san", "debt_to_assets"),
            ("ty so no vay tren von chu so huu", "debt_to_equity"),
            ("loi nhuan sau thue chua phan phoi", "retained_earnings"),
            ("doanh thu thuan ve ban hang va cung cap dich vu", "revenue"),
            ("doanh thu thuan", "revenue"),
            ("gia von hang ban", "cost_of_goods_sold"),
            ("loi nhuan gop ve ban hang va cung cap dich vu", "gross_profit"),
            ("loi nhuan gop", "gross_profit"),
            ("doanh thu hoat dong tai chinh", "financial_income"),
            ("chi phi tai chinh", "financial_expense"),
            ("chi phi ban hang", "selling_expense"),
            ("chi phi quan ly doanh nghiep", "general_admin_expense"),
            ("loi nhuan thuan tu hoat dong kinh doanh", "operating_profit"),
            ("tong loi nhuan ke toan truoc thue", "profit_before_tax"),
            ("loi nhuan sau thue cua cong ty me", "parent_profit"),
            ("loi nhuan sau thue thu nhap doanh nghiep", "profit_after_tax"),
            ("loi nhuan sau thue", "profit_after_tax"),
            ("lai co ban tren co phieu", "eps"),
            ("thu nhap tren moi co phan cua 4 quy gan nhat", "eps_ttm"),
            ("gia tri so sach cua co phieu", "bvps"),
            ("chi so gia thi truong tren thu nhap", "pe"),
            ("p/e", "pe"),
            ("chi so gia thi truong tren gia tri so sach", "pb"),
            ("p/b", "pb"),
            ("ty suat loi nhuan gop bien", "gross_margin"),
            ("ty suat sinh loi tren doanh thu thuan", "net_margin"),
            ("ty suat loi nhuan tren von chu so huu binh quan", "roe"),
            ("roea", "roe"),
            ("ty suat loi nhuan tren tong tai san binh quan", "roa"),
            ("roaa", "roa"),
            ("ty so thanh toan hien hanh", "current_ratio"),
            ("kha nang thanh toan lai vay", "interest_coverage"),
            ("ty so no tren tong tai san", "debt_to_assets"),
            ("ty so no vay tren von chu so huu", "debt_to_equity"),
            ("tai san ngan han khac", "other_current_assets"),
            ("tai san ngan han", "current_assets"),
            ("tien va cac khoan tuong duong tien", "cash"),
            ("cac khoan dau tu tai chinh ngan han", "short_term_investments"),
            ("cac khoan phai thu ngan han", "short_term_receivables"),
            ("hang ton kho", "inventory"),
            ("tai san dai han", "long_term_assets"),
            ("tai san co dinh", "fixed_assets"),
            ("bat dong san dau tu", "investment_properties"),
            ("cac khoan dau tu tai chinh dai han", "long_term_investments"),
            ("tong cong tai san", "total_assets"),
            ("no phai tra", "total_liabilities"),
            ("no ngan han", "current_liabilities"),
            ("no dai han", "long_term_liabilities"),
            ("von chu so huu", "equity"),
            ("von dau tu cua chu so huu", "owner_capital"),
            ("thang du von co phan", "share_premium"),
            ("loi nhuan sau thue chua phan phoi", "retained_earnings"),
            ("tong cong nguon von", "total_capital"),
            ("tong nguon von", "total_capital"),
            ("thu nhap lai thuan", "net_interest_income"),
            ("thu nhap lai va cac khoan thu nhap tuong tu", "interest_income"),
            ("chi phi lai va cac chi phi tuong tu", "interest_expense"),
            ("lai/lo thuan tu hoat dong dich vu", "net_fee_income"),
            ("lai lo thuan tu hoat dong dich vu", "net_fee_income"),
            ("lai/lo thuan tu hoat dong kinh doanh ngoai hoi", "fx_trading_income"),
            ("lai lo thuan tu hoat dong kinh doanh ngoai hoi", "fx_trading_income"),
            ("lai/lo thuan tu mua ban chung khoan kinh doanh", "trading_securities_income"),
            ("lai lo thuan tu mua ban chung khoan kinh doanh", "trading_securities_income"),
            ("lai/lo thuan tu mua ban chung khoan dau tu", "investment_securities_income"),
            ("lai lo thuan tu mua ban chung khoan dau tu", "investment_securities_income"),
            ("thu nhap tu gop von mua co phan", "dividend_income"),
            ("chi phi hoat dong", "operating_expense"),
            ("loi nhuan thuan tu hoat dong kinh doanh truoc chi phi du phong rui ro tin dung", "pre_provision_operating_profit"),
            ("chi phi du phong rui ro tin dung", "credit_provision_expense"),
            ("tong loi nhuan truoc thue", "profit_before_tax"),
            ("loi nhuan sau thue cua co dong cua ngan hang me", "parent_profit"),
            ("loi nhuan sau thue cua co dong ngan hang me", "parent_profit"),
            ("tong cong tai san", "total_assets"),
            ("tong tai san", "total_assets"),
            ("tien mat vang bac da quy", "cash_and_gold"),
            ("tien gui tai nhnn", "deposit_at_state_bank"),
            ("tien gui tai ngan hang nha nuoc viet nam", "deposit_at_state_bank"),
            ("tien vang gui tai cac tctd khac va cho vay cac tctd khac", "interbank_assets"),
            ("tien vang gui tai cac tctd khac va cho vay cac tctd khac", "interbank_assets"),
            ("cho vay va cho thue tai chinh khach hang", "customer_loans"),
            ("cho vay khach hang", "customer_loans"),
            ("du phong rui ro cho vay khach hang", "loan_loss_reserve"),
            ("chung khoan kinh doanh", "trading_securities"),
            ("chung khoan dau tu", "investment_securities"),
            ("tien gui cua khach hang", "customer_deposits"),
            ("cac khoan no chinh phu va nhnn", "government_and_state_bank_debt"),
            ("tien gui va vay cac tctd khac", "interbank_liabilities"),
            ("phat hanh giay to co gia", "valuable_papers_issued"),
            ("ty le no xau", "npl_ratio"),
            ("ty le bao phu no xau", "loan_loss_coverage"),
            ("nim", "nim"),
            ("casa", "casa_ratio"),
            ("roe", "roe"),
            ("roa", "roa"),
            ("eps", "eps"),
            ("bvps", "bvps"),
        ]
        for candidate, field in sorted(mapping, key=lambda item: len(item[0]), reverse=True):
            if candidate in normalized:
                return field
        return None

    def _is_valid_financial_period(self, period: dict[str, Any]) -> bool:
        meaningful = 0
        for key in FINANCIAL_METRIC_FIELDS:
            value = period.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                meaningful += 1
        return meaningful >= 3

    def _parse_number(self, value: Any) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized_missing = self._normalize_text(text)
        if normalized_missing in {"-", "--", "n/a", "na", "none", "chua co du lieu"}:
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

    def _extract_numeric_values(self, text: str) -> list[float | None]:
        matches = re.findall(r"\(?-?\d[\d,.]*\)?", text)
        values: list[float | None] = []
        for match in matches:
            parsed_period = self._parse_period(match)
            if parsed_period:
                continue
            values.append(self._parse_number(match))
        return values

    def _extract_text_lines(self, html_text: str) -> list[str]:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "\n", html_text or "")
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</(div|tr|td|th|p|li|span|section|article|h[1-6])>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_lib.unescape(text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return [line for line in lines if line]

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
        normalized = normalized.lower().replace("đ", "d")
        normalized = re.sub(r"[^a-z0-9/%\s.-]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _detect_unit(self, html_text: str) -> str | None:
        text = " ".join(self._extract_text_lines(html_text))
        match = re.search(r"Đơn vị\s*:?\s*(Tỷ đồng|Triệu đồng|Nghìn đồng|Đồng|VND)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        normalized = self._normalize_text(text)
        if "ty dong" in normalized:
            return "Tỷ đồng"
        if "trieu dong" in normalized:
            return "Triệu đồng"
        if "nghin dong" in normalized:
            return "Nghìn đồng"
        return None

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
        return self.cache_dir / f"vietstock_financial_{cache_kind}_{digest}.json"

    def _read_cache(self, url: str, cache_kind: str) -> str | None:
        path = self._cache_path(url, cache_kind=cache_kind)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_at = float(payload.get("cached_at") or 0)
            if time.time() - cached_at > self.settings.effective_vietstock_financial_cache_ttl_seconds:
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
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_bctc_rendered.html").write_text(html_text, encoding="utf-8")
        except Exception:
            return

    def _save_extraction_debug(self, symbol: str, source_url: str, result: dict[str, Any], *, render_status: str) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        periods = result.get("periods") if isinstance(result.get("periods"), list) else []
        period_headers = [period.get("period") for period in periods if isinstance(period, dict)]
        labels_found = sorted(
            {
                key
                for period in periods
                if isinstance(period, dict)
                for key, value in period.items()
                if key not in {"period", "year", "quarter"} and value is not None
            }
        )
        payload = {
            "source_url": source_url,
            "render_status": render_status,
            "wait_strategy_used": self._safe_wait_until(self.settings.effective_vietstock_financial_browser_wait_until),
            "selectors_found": [],
            "period_headers_found": period_headers,
            "financial_row_labels_found": labels_found,
            "final_valid_bctc_periods": periods,
            "warnings": result.get("warnings") or [],
            "technical_warnings": result.get("technical_warnings") or [],
            "status": result.get("status"),
        }
        try:
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{normalize_symbol(symbol)}_vietstock_bctc_extraction.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / f"{normalize_symbol(symbol)}_financial_mapping_debug.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _safe_wait_until(self, value: str | None) -> str:
        wait_until = (value or "domcontentloaded").strip().lower()
        if wait_until == "networkidle":
            return "domcontentloaded"
        if wait_until not in {"commit", "domcontentloaded", "load"}:
            return "domcontentloaded"
        return wait_until

    def _result(
        self,
        source_url: str,
        periods: list[dict[str, Any]],
        warnings: list[str],
        technical_warnings: list[str],
        status: str,
        unit: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "source_url": source_url,
            "fetched_at": now_iso(),
            "unit": unit or self.settings.effective_vietstock_financial_unit,
            "periods": periods,
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


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            cell = re.sub(r"\s+", " ", " ".join(self._current_cell)).strip()
            self._current_row.append(cell)
            self._in_cell = False
            self._current_cell = []
        elif tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False
            self._current_table = []
