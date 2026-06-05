from __future__ import annotations

import logging
import re
from typing import Any, Dict, Tuple

from bs4 import BeautifulSoup

from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.models.records import empty_financial_record, empty_market_record
from vietstock_crawler.parsers.common import (
    find_value_in_text_near_label,
    get_latest_metric_value,
    html_to_lines,
    is_error_page,
)
from vietstock_crawler.parsers.financial_parser import apply_bctt_fallback_to_financial
from vietstock_crawler.parsers.market_parser import extract_current_price, extract_foreign_volume, validate_market_price
from vietstock_crawler.parsers.trading_stats_parser import crawl_trading_stats
from vietstock_crawler.utils.number_utils import normalize_number
from vietstock_crawler.utils.url_utils import is_wrong_profile_html, make_company_url

def crawl_company(symbol: str, slug: str, browser: VietstockBrowser, profile_url: str = "", crawl_financial: bool = True):
    try:
        url = make_company_url(symbol, slug, profile_url)
    except Exception as e:
        source = profile_url or ""
        return (
            empty_market_record(symbol, source, str(e), "Missing profile slug/profile_url"),
            empty_financial_record(symbol, source, str(e), "Missing profile slug/profile_url"),
        )

    market = empty_market_record(symbol, url)
    financial = empty_financial_record(symbol, url)

    try:
        html = browser.get_html(url)
        if is_error_page(html):
            market["error"] = "Invalid URL"
            financial["error"] = "Invalid URL"
            return market, financial

        if is_wrong_profile_html(html, symbol):
            msg = f"Wrong page loaded for {symbol}: got trading stats page instead of company profile. URL={url}"
            market["error"] = msg
            financial["error"] = msg
            return market, financial

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        lines = html_to_lines(html)
        title = soup.find("title")
        title_text = title.get_text(" ", strip=True) if title else ""

        market["is_valid_url"] = True
        market["company_name"] = title_text
        financial["is_valid_url"] = True
        financial["company_name"] = title_text

        # MARKET
        market["price"] = extract_current_price(lines, text)
        market["open"] = find_value_in_text_near_label(text, "Mở cửa")
        market["high"] = find_value_in_text_near_label(text, "Cao nhất")
        market["low"] = find_value_in_text_near_label(text, "Thấp nhất")
        market["reference"] = find_value_in_text_near_label(text, "Tham chiếu")
        market["volume"] = find_value_in_text_near_label(text, "KLGD")
        market["market_cap"] = find_value_in_text_near_label(text, "Vốn hóa")
        market["bid_volume"] = find_value_in_text_near_label(text, "Dư mua")
        market["ask_volume"] = find_value_in_text_near_label(text, "Dư bán")

        # Parse from overview trading table on the profile page (for volume fallback, reference, price change)
        try:
            table = soup.find("table", class_="overview-trading__table")
            if table:
                tbody = table.find("tbody")
                if tbody:
                    first_tr = tbody.find("tr")
                    if first_tr:
                        cells = [c.get_text(" ", strip=True) for c in first_tr.find_all("td")]
                        if len(cells) >= 4:
                            if market["volume"] is None:
                                market["volume"] = normalize_number(cells[3])
                            
                            change_str = cells[2]
                            c_val, c_pct = None, None
                            if change_str.strip() == "0":
                                c_val = 0.0
                                c_pct = 0.0
                            else:
                                m = re.match(r"\s*([-+−]?\s*[\d,.]+)\s*\(\s*([-+−]?\s*[\d,.]+)%\s*\)", change_str.replace("−", "-"))
                                if m:
                                    c_val = normalize_number(m.group(1).replace(" ", ""))
                                    c_pct = normalize_number(m.group(2).replace(" ", ""))
                            
                            market["price_change"] = c_val
                            market["price_change_percent"] = c_pct
                            
                            if market["reference"] is None and market["price"] is not None and c_val is not None:
                                market["reference"] = market["price"] - c_val
        except Exception as e:
            logging.warning(f"Failed to parse overview table fields for {symbol}: {e}")

        market["foreign_buy"] = extract_foreign_volume(html, lines, text, ["NN mua", "Nước ngoài mua"])
        market["foreign_sell"] = extract_foreign_volume(html, lines, text, ["NN bán", "Nước ngoài bán"])
        if market["foreign_buy"] is not None and market["foreign_sell"] is not None:
            market["foreign_net"] = market["foreign_buy"] - market["foreign_sell"]
        market["eps"] = find_value_in_text_near_label(text, "EPS")
        market["pe"] = find_value_in_text_near_label(text, "P/E")
        market["forward_pe"] = find_value_in_text_near_label(text, "F P/E")
        market["bvps"] = find_value_in_text_near_label(text, "BVPS")
        market["pb"] = find_value_in_text_near_label(text, "P/B")
        market["beta"] = find_value_in_text_near_label(text, "Beta")
        market["ros"] = get_latest_metric_value(html, lines, ["ROS"], max_abs=1000)
        market["roea"] = get_latest_metric_value(html, lines, ["ROEA"], max_abs=1000)
        market["roaa"] = get_latest_metric_value(html, lines, ["ROAA"], max_abs=1000)
        # Vietstock thường không có dòng ROE riêng ở box này; dùng ROEA làm ROE fallback.
        market["roe"] = get_latest_metric_value(html, lines, ["ROE"], max_abs=1000) or market["roea"]
        market["close"] = market["price"] or market["reference"] or market["open"]
        if market["price"] is None:
            market["price"] = market["close"]

        # Không ghi note gây nhiễu nếu chỉ thiếu foreign/ROE fallback.
        market["note"] = ""

        # Chặn các case parser lấy nhầm mức tăng/giảm làm giá hiện tại.
        # Ví dụ VPL giá thật 93,500 nhưng mức tăng 1,700; nếu bị lệch xa High/Low thì bỏ trống thay vì ghi sai.
        validate_market_price(market)

        # Nếu không bật ENABLE_FINANCIAL_DATA thì dừng tại MARKET_DATA.
        # Không parse bảng tài chính và đặc biệt KHÔNG mở tab BCTT.
        if not crawl_financial:
            return market, financial

        # FINANCIAL: Vietstock hiển thị các cột cũ -> mới, nên luôn lấy giá trị ngoài cùng bên phải.
        # Nhóm "Kết quả kinh doanh"
        financial["net_revenue"] = get_latest_metric_value(
            html, lines,
            ["Doanh thu thuần", "Thu nhập lãi thuần"],
            min_abs=1000,
        )
        financial["gross_profit"] = get_latest_metric_value(
            html, lines,
            ["Lợi nhuận gộp", "Lãi gộp"],
            min_abs=1000,
        )
        financial["net_profit_from_operating_activity"] = get_latest_metric_value(
            html, lines,
            ["LN thuần từ HĐKD", "Lợi nhuận thuần từ HĐKD", "Lợi nhuận thuần từ hoạt động kinh doanh"],
            min_abs=1000,
        )
        financial["corporate_income_tax"] = get_latest_metric_value(
            html, lines,
            ["LNST thu nhập DN", "Chi phí thuế TNDN", "Thuế TNDN", "Thuế thu nhập doanh nghiệp"],
            min_abs=1,
        )

        # Nhóm ngân hàng / tài chính vẫn giữ lại các chỉ số cũ.
        financial["net_interest_income"] = get_latest_metric_value(html, lines, ["Thu nhập lãi thuần"], min_abs=1000)
        financial["operating_expense"] = get_latest_metric_value(html, lines, ["Chi phí hoạt động"], min_abs=1000)
        financial["total_operating_income"] = get_latest_metric_value(html, lines, ["Tổng TNTT", "Tổng thu nhập hoạt động"], min_abs=1000)
        financial["profit_before_tax"] = get_latest_metric_value(html, lines, ["LNTT", "Lợi nhuận trước thuế"], min_abs=1000)
        financial["profit_after_tax"] = get_latest_metric_value(html, lines, ["Tổng LNST", "Lợi nhuận sau thuế"], min_abs=1000)
        financial["parent_company_profit"] = get_latest_metric_value(
            html, lines,
            ["LNST của CĐ", "LNST của CĐ cty mẹ", "LNST của cổ đông công ty mẹ", "LNST của Ngân hàng mẹ", "LNST của Công ty mẹ"],
            min_abs=1000,
        )

        # Nhóm "Cân đối kế toán"
        financial["current_assets"] = get_latest_metric_value(html, lines, ["Tài sản ngắn hạn"], min_abs=1000)
        financial["total_assets"] = get_latest_metric_value(html, lines, ["Tổng tài sản"], min_abs=1000)
        financial["customer_loans"] = get_latest_metric_value(html, lines, ["Cho vay khách hàng"], min_abs=1000)
        financial["customer_deposits"] = get_latest_metric_value(html, lines, ["Tiền gửi của khách hàng"], min_abs=1000)
        financial["liabilities"] = get_latest_metric_value(html, lines, ["Nợ phải trả"], min_abs=1000)
        financial["current_liabilities"] = get_latest_metric_value(html, lines, ["Nợ ngắn hạn"], min_abs=1000)
        financial["equity"] = get_latest_metric_value(html, lines, ["Vốn chủ sở hữu", "Vốn và các quỹ"], min_abs=1000)
        financial["retained_earnings"] = get_latest_metric_value(html, lines, ["Lợi nhuận chưa phân phối"], min_abs=1000)

        # Nhóm "Chỉ số tài chính"
        # Các chỉ số EPS/BVPS/P/E lấy cùng nguồn quick-box với MARKET_DATA để không lệch giữa 2 sheet.
        financial["eps_4q"] = market.get("eps") or get_latest_metric_value(html, lines, ["EPS 4 quý"], min_abs=1)
        financial["bvps"] = market.get("bvps") or get_latest_metric_value(html, lines, ["BVPS cơ bản", "BVPS"], min_abs=1)
        financial["pe_basic"] = market.get("pe") or get_latest_metric_value(html, lines, ["P/E cơ bản"], max_abs=1000)
        financial["ros"] = market.get("ros") or get_latest_metric_value(html, lines, ["ROS"], max_abs=1000)
        financial["roea"] = get_latest_metric_value(html, lines, ["ROEA"], max_abs=1000) or market.get("roea")
        financial["roaa"] = get_latest_metric_value(html, lines, ["ROAA"], max_abs=1000) or market.get("roaa")
        financial["roe"] = get_latest_metric_value(html, lines, ["ROE"], max_abs=1000) or financial["roea"] or market.get("roe")

        # Nếu profile thiếu các dòng KQKD/CĐKT, mở thêm tab BCTT để bù dữ liệu tài chính.
        apply_bctt_fallback_to_financial(symbol, browser, financial)

        # Không ghi note gây nhiễu nếu chỉ thiếu một vài chỉ số không có trên một số ngành.
        financial["note"] = ""

    except Exception as e:
        logging.exception("Company crawl failed %s", symbol)
        market["error"] = str(e)
        financial["error"] = str(e)

    return market, financial



def crawl_symbol_bundle(
    symbol: str,
    slug: str,
    profile_url: str,
    trading_stats_url: str,
    browser: VietstockBrowser,
    crawl_financial: bool,
    crawl_trading: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any] | None]:
    """Crawl all enabled record types for a single symbol."""
    market, financial = crawl_company(
        symbol=symbol,
        slug=slug,
        browser=browser,
        profile_url=profile_url,
        crawl_financial=crawl_financial,
    )
    trading = crawl_trading_stats(symbol=symbol, browser=browser, trading_stats_url=trading_stats_url) if crawl_trading else None
    return market, financial, trading
