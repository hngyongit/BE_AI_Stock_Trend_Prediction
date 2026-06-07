from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Dict

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from vietstock_crawler.config.constants import AD_BLOCK_KEYWORDS, REQUEST_HEADERS
from vietstock_crawler.config.settings import (
    BLOCK_ADS,
    BCTT_PAGE_WAIT_MS,
    CLOSE_POPUPS,
    MAX_PAGE_RETRIES,
    PAGE_RETRY_SLEEP_SECONDS,
    PAGE_TIMEOUT_MS,
    PAGE_WAIT_MS,
    PLAYWRIGHT_WAIT_UNTIL,
)
from vietstock_crawler.utils.url_utils import is_same_navigation_target
from vietstock_crawler.utils.number_utils import normalize_number
from bs4 import BeautifulSoup
import datetime


def fetch_html_requests(url: str, timeout: float = 30.0) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text or ""

class VietstockBrowser:
    def __init__(self, timeout: float | None = None):
        self.timeout = timeout
        self.deadline = time.time() + timeout if timeout else None
        self.html_cache = {}

    def _check_deadline(self):
        if self.deadline and time.time() >= self.deadline:
            raise TimeoutError(f"Timeout > {self.timeout}s")

    def _get_remaining_timeout(self, default_timeout_ms: float) -> float:
        if not self.deadline:
            return default_timeout_ms
        remaining = (self.deadline - time.time()) * 1000.0
        return max(1.0, min(remaining, default_timeout_ms))

    def _wait_for_timeout_safe(self, ms: float):
        self._check_deadline()
        remaining = self._get_remaining_timeout(ms)
        self.page.wait_for_timeout(remaining)

    def __enter__(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        )
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000},
            locale="vi-VN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        )

        def block_heavy_resources(route):
            req = route.request
            url = req.url.lower()

            # Không chặn stylesheet: Vietstock cần CSS/layout để bảng tài chính render ổn.
            if req.resource_type in ["image", "media", "font"]:
                return route.abort()

            if BLOCK_ADS and any(keyword in url for keyword in AD_BLOCK_KEYWORDS):
                return route.abort()

            return route.continue_()

        self.context.route("**/*", block_heavy_resources)
        self.page = self.context.new_page()
        timeout_ms = self._get_remaining_timeout(PAGE_TIMEOUT_MS)
        self.page.set_default_timeout(timeout_ms)
        self.page.set_default_navigation_timeout(timeout_ms)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for obj_name in ["page", "context", "browser"]:
            try:
                obj = getattr(self, obj_name, None)
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if getattr(self, "pw", None):
                self.pw.stop()
        except Exception:
            pass

    def _is_network_error(self, error: Exception) -> bool:
        msg = str(error)
        signals = [
            "ERR_NETWORK_CHANGED", "ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED",
            "ERR_ADDRESS_UNREACHABLE", "ERR_CONNECTION", "ERR_CONNECTION_RESET",
            "ERR_CONNECTION_CLOSED", "ERR_CONNECTION_REFUSED", "ERR_TIMED_OUT",
            "Timeout", "Navigation timeout", "Target closed", "Page closed",
            "Page crashed", "Target crashed", "Target page, context or browser has been closed",
            "Browser closed", "net::",
        ]
        return any(signal in msg for signal in signals)

    def _reset_page(self):
        try:
            self.page.close()
        except Exception:
            pass
        self.page = self.context.new_page()
        timeout_ms = self._get_remaining_timeout(PAGE_TIMEOUT_MS)
        self.page.set_default_timeout(timeout_ms)
        self.page.set_default_navigation_timeout(timeout_ms)

    def close_ads_and_popups(self):
        if not CLOSE_POPUPS:
            return

        self._check_deadline()
        selectors = [
            "button:has-text('×')", "button:has-text('x')", "button:has-text('X')",
            "a:has-text('×')", ".close", ".btn-close", ".popup-close", ".modal-close",
            ".fancybox-close", ".mfp-close", "[aria-label='Close']", "[aria-label='close']",
            "[title='Close']", "[title='Đóng']",
        ]

        for selector in selectors:
            try:
                self._check_deadline()
                locator = self.page.locator(selector)
                count = min(locator.count(), 8)
                for idx in range(count):
                    try:
                        self._check_deadline()
                        item = locator.nth(idx)
                        if item.is_visible(timeout=self._get_remaining_timeout(250)):
                            item.click(timeout=self._get_remaining_timeout(600), force=True)
                            self._wait_for_timeout_safe(150)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            self._check_deadline()
            self.page.keyboard.press("Escape")
            self._wait_for_timeout_safe(150)
        except Exception:
            pass

        # Ẩn overlay quảng cáo lớn nếu còn che màn hình.
        try:
            self._check_deadline()
            self.page.evaluate("""
                () => {
                    const vw = window.innerWidth || 1400;
                    const vh = window.innerHeight || 1000;
                    for (const el of Array.from(document.querySelectorAll('body *'))) {
                        try {
                            const st = window.getComputedStyle(el);
                            const zi = parseInt(st.zIndex || '0', 10);
                            if (!Number.isFinite(zi) || zi < 1000) continue;
                            if (!['fixed', 'absolute', 'sticky'].includes(st.position)) continue;
                            const r = el.getBoundingClientRect();
                            const area = Math.max(0, r.width) * Math.max(0, r.height);
                            if (area > vw * vh * 0.30) el.style.display = 'none';
                        } catch (e) {}
                    }
                }
            """)
            self._wait_for_timeout_safe(100)
        except Exception:
            pass

    def get_html(self, url: str, use_cache: bool = True, bctt_mode: bool = False) -> str:
        if use_cache and url in self.html_cache:
            return self.html_cache[url]

        last_error = None
        for attempt in range(1, MAX_PAGE_RETRIES + 1):
            try:
                self._check_deadline()
                logging.info("Open attempt %s/%s: %s", attempt, MAX_PAGE_RETRIES, url)
                try:
                    remaining_ms = self._get_remaining_timeout(PAGE_TIMEOUT_MS)
                    self.page.goto(url, wait_until=PLAYWRIGHT_WAIT_UNTIL, timeout=remaining_ms)
                except PlaywrightTimeoutError as e:
                    last_error = e
                    current_url = getattr(self.page, "url", "")
                    # Không dùng content hiện tại nếu timeout khiến page vẫn nằm ở URL cũ.
                    if not is_same_navigation_target(current_url, url):
                        raise RuntimeError(f"Navigation timeout and current URL is stale. target={url}, current={current_url}")
                    logging.warning("Page timeout but target URL loaded, try current content: %s", url)

                current_url = getattr(self.page, "url", "")
                if not is_same_navigation_target(current_url, url):
                    raise RuntimeError(f"Navigation ended at unexpected URL. target={url}, current={current_url}")

                self._wait_for_timeout_safe(PAGE_WAIT_MS)
                self.close_ads_and_popups()

                if bctt_mode:
                    # Tab BCTT có nút Quý/Năm và đơn vị Nghìn/Triệu/Tỷ đồng.
                    # Ép chọn Quý + Tỷ đồng để đúng đơn vị cột BCTT (... bil VND).
                    for label in ["Quý", "Tỷ đồng"]:
                        try:
                            self.close_ads_and_popups()
                            self.page.get_by_text(label, exact=True).click(timeout=self._get_remaining_timeout(1200))
                            self._wait_for_timeout_safe(400)
                            self.close_ads_and_popups()
                        except Exception:
                            pass
                    try:
                        self._wait_for_timeout_safe(BCTT_PAGE_WAIT_MS)
                    except Exception:
                        pass

                for y in [900, 1800, 2600, 0]:
                    try:
                        self._check_deadline()
                        self.page.evaluate(f"window.scrollTo(0, {y})")
                        self._wait_for_timeout_safe(300)
                        self.close_ads_and_popups()
                    except Exception:
                        pass

                if bctt_mode:
                    # Vietstock dùng bảng có thanh cuộn ngang; cột mới nhất nằm ngoài cùng bên phải.
                    # Scroll tất cả container ngang sang phải để nếu DOM lazy-render thì cột mới nhất xuất hiện.
                    try:
                        self._check_deadline()
                        self.page.evaluate("""
                            () => {
                                const all = Array.from(document.querySelectorAll('*'));
                                for (const el of all) {
                                    try {
                                        if (el.scrollWidth && el.clientWidth && el.scrollWidth > el.clientWidth + 50) {
                                            el.scrollLeft = el.scrollWidth;
                                        }
                                    } catch (e) {}
                                }
                                window.scrollTo(0, 0);
                            }
                        """)
                        self._wait_for_timeout_safe(800)
                    except Exception:
                        pass

                self._check_deadline()
                html = self.page.content()
                current_url = getattr(self.page, "url", "")
                if not is_same_navigation_target(current_url, url):
                    raise RuntimeError(f"Stale HTML detected. target={url}, current={current_url}")
                if html and len(html) > 5000:
                    if use_cache:
                        self.html_cache[url] = html
                    return html
                raise RuntimeError(f"HTML quá ngắn hoặc rỗng: {len(html) if html else 0} chars")

            except Exception as e:
                last_error = e
                # Check dynamic timeout deadline before doing any retry sleep
                if self.deadline and time.time() >= self.deadline:
                    raise TimeoutError(f"Timeout > {self.timeout}s") from e

                if self._is_network_error(e):
                    wait_seconds = PAGE_RETRY_SLEEP_SECONDS * attempt
                    if self.deadline and time.time() + wait_seconds >= self.deadline:
                        raise TimeoutError(f"Timeout > {self.timeout}s") from e
                    logging.warning(
                        "Network/page error. Retry %s/%s sau %.1fs. URL=%s. Error=%s",
                        attempt, MAX_PAGE_RETRIES, wait_seconds, url, str(e)[:350]
                    )
                    time.sleep(wait_seconds)
                    self._reset_page()
                    continue

                wait_seconds = min(3 * attempt, 15)
                if self.deadline and time.time() + wait_seconds >= self.deadline:
                    raise TimeoutError(f"Timeout > {self.timeout}s") from e
                logging.warning(
                    "Page error. Retry %s/%s sau %.1fs. URL=%s. Error=%s",
                    attempt, MAX_PAGE_RETRIES, wait_seconds, url, str(e)[:350]
                )
                time.sleep(wait_seconds)
                self._reset_page()

        # Fallback requests: dùng khi Playwright lỗi do quảng cáo/popup/network nhưng trang profile vẫn trả HTML.
        try:
            self._check_deadline()
            logging.warning("Playwright failed; trying direct requests fallback: %s", url)
            remaining_sec = max(1.0, self.deadline - time.time()) if self.deadline else 30.0
            html = fetch_html_requests(url, timeout=remaining_sec)
            if html and len(html) > 5000:
                if use_cache:
                    self.html_cache[url] = html
                return html
        except Exception as e:
            last_error = f"{last_error}; requests fallback failed: {e}"

        raise RuntimeError(f"Không mở được URL sau {MAX_PAGE_RETRIES} lần: {url}. Last error: {last_error}")

    def click_load_more(self, timeout: float = 5.0) -> bool:
        """Click 'Xem thêm' button on Vietstock trading stats page and wait for table to append data.
        Returns True if clicked and new rows were appended successfully within timeout."""
        try:
            # Get current row count before click
            html_before = self.page.content()
            prev_row_count = self.get_table_row_count(html_before)

            # First, try to scroll to bottom to reveal load-more button if it exists
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.page.wait_for_timeout(500)
            
            # Try multiple selectors for "Xem thêm" button
            selectors = [
                "button:has-text('Xem thêm')",
                "a:has-text('Xem thêm')",
                "button:has-text('xem thêm')",
                "button:has-text('Xem Thêm')",
                "a:has-text('Xem Thêm')",
                ".load-more",
                ".btn-load-more",
                ".btn_xemthem",
                "[class*='load-more']",
                "[class*='xem-them']",
                "[class*='xemthem']",
                "button[class*='load']",
                "a[class*='load']",
                # More generic: any button with "thêm" text
                "button:has-text('thêm')",
                "a:has-text('thêm')",
                # Vietstock specific selectors
                ".btn-xem-them",
                ".btn_xem-them",
                "#btnLoadMore",
                "#loadMoreBtn",
                # Icon-based selectors (chevron, arrow icons often used for load more)
                "button:has-text('▶')",
                "button:has-text('▼')",
                "button:has-text('>')",
                "button:has-text('+')",
                "[aria-label*='Xem thêm']",
                "[title*='Xem thêm']",
            ]
            
            clicked = False
            for selector in selectors:
                try:
                    locator = self.page.locator(selector)
                    if locator.count() > 0:
                        btn = locator.first
                        if btn.is_visible(timeout=500):  # Short timeout for visibility check
                            btn.click(timeout=1000)
                            logging.info("Clicked load-more button with selector: %s", selector)
                            clicked = True
                            break
                except Exception:
                    continue
            
            # Try finding by evaluating page for buttons containing "Xem thêm" text
            if not clicked:
                try:
                    clicked = self.page.evaluate("""
                        () => {
                            const buttons = Array.from(document.querySelectorAll('button, a, div, span'));
                            for (const btn of buttons) {
                                const text = (btn.textContent || '').toLowerCase().replace(/\s+/g, ' ').trim();
                                if (text.includes('xem thêm') || text.includes('xem them') || text.includes('them')) {
                                    // Check if it looks like a button
                                    const style = window.getComputedStyle(btn);
                                    const hasPointer = style.cursor === 'pointer';
                                    const isButton = btn.tagName === 'BUTTON' || btn.tagName === 'A';
                                    const hasClickHandler = btn.onclick || btn.getAttribute('onclick');
                                    if (hasPointer || isButton || hasClickHandler) {
                                        btn.click();
                                        return true;
                                    }
                                }
                            }
                            return false;
                        }
                    """)
                    if clicked:
                        logging.info("Clicked load-more button via page evaluation")
                except Exception:
                    pass
            
            if not clicked:
                return False
            
            # Wait for table to append more data (row count increases)
            start_time = time.time()
            while time.time() - start_time < timeout:
                self.page.wait_for_timeout(200)
                html_after = self.page.content()
                new_row_count = self.get_table_row_count(html_after)
                if new_row_count > prev_row_count:
                    logging.info("Table successfully appended data: row count went from %d to %d", prev_row_count, new_row_count)
                    return True
            
            logging.warning("Timeout waiting for table to append data after click. Row count remained at %d", prev_row_count)
            return False
        except Exception as e:
            logging.warning("Error in click_load_more: %s", e)
            return False

    def get_table_dates(self, html: str) -> tuple[date | None, date | None]:
        """Extract min and max dates from historical price table in HTML. Returns (min_date, max_date)."""
        soup = BeautifulSoup(html, "html.parser")
        dates_found = []
        
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                if len(cells) < 2:
                    continue
                
                # Try to parse date from first cells
                for cell in cells[:3]:
                    # Try formats: dd/mm/yyyy, dd/mm/yy
                    for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
                        try:
                            parsed = datetime.strptime(cell.strip(), fmt).date()
                            dates_found.append(parsed)
                            break
                        except ValueError:
                            continue
        
        if dates_found:
            return min(dates_found), max(dates_found)
        return None, None

    def get_table_row_count(self, html: str) -> int:
        """Count data rows in historical price table."""
        soup = BeautifulSoup(html, "html.parser")
        row_count = 0
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 8:  # Valid data row
                    row_count += 1
        return row_count
