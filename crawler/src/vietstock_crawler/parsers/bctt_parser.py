from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from vietstock_crawler.parsers.common import extract_latest_period_label, get_latest_metric_value, html_to_lines, is_error_page
from vietstock_crawler.utils.url_utils import make_bctt_url

def get_latest_metric_from_many_htmls(
    htmls: List[str],
    labels: List[str],
    min_abs: Optional[float] = None,
    max_abs: Optional[float] = None,
) -> Optional[float]:
    """
    Thử nhiều version HTML của cùng trang:
    - HTML ban đầu.
    - HTML sau khi scroll ngang sang phải.

    Lý do: tab BCTT có bảng ngang, cột mới nhất nằm ngoài cùng bên phải,
    một số trường hợp DOM chỉ render phần đang nhìn thấy.
    """
    for html in htmls:
        if not html:
            continue
        lines = html_to_lines(html)
        value = get_latest_metric_value(
            html=html,
            lines=lines,
            labels=labels,
            min_abs=min_abs,
            max_abs=max_abs,
            scan_next=20,
        )
        if value is not None:
            return value
    return None


def crawl_bctt_for_trading_stats(symbol: str, browser: VietstockBrowser) -> Dict[str, Any]:
    """
    Crawl thêm tab BCTT:
    https://finance.vietstock.vn/<MÃ>/tai-chinh.htm?tab=BCTT

    Lấy dữ liệu cột mới nhất ngoài cùng bên phải.
    Nếu bảng bị lazy-render theo thanh cuộn ngang, hàm sẽ lấy thêm HTML sau khi scroll ngang.
    """
    url = make_bctt_url(symbol)
    data: Dict[str, Any] = {
        "bctt_source": url,
        "bctt_is_valid_url": False,
        "bctt_latest_period": "",
    }

    try:
        # Lấy 2 bản HTML: bản thường và bản đã scroll ngang về cột mới nhất.
        html_initial = browser.get_html(url, use_cache=False, bctt_mode=True)
        html_right = browser.get_html(url, use_cache=False, bctt_mode=True)
        htmls = [html_right, html_initial]

        if is_error_page(html_initial) and is_error_page(html_right):
            data["note"] = "BCTT invalid URL"
            return data

        data["bctt_is_valid_url"] = True
        data["bctt_latest_period"] = extract_latest_period_label(html_right) or extract_latest_period_label(html_initial)

        def latest(labels: List[str], min_abs: Optional[float] = None, max_abs: Optional[float] = None) -> Optional[float]:
            return get_latest_metric_from_many_htmls(htmls, labels, min_abs=min_abs, max_abs=max_abs)

        data["bctt_net_revenue"] = latest(
            ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "Doanh thu thuần", "Thu nhập lãi thuần"],
            min_abs=1,
        )
        data["bctt_cost_of_goods_sold"] = latest(["Giá vốn hàng bán"], min_abs=1)
        data["bctt_gross_profit"] = latest(
            ["Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "Lợi nhuận gộp", "Lãi gộp"],
            min_abs=1,
        )
        data["bctt_financial_income"] = latest(["Doanh thu hoạt động tài chính"], max_abs=10_000_000_000)
        data["bctt_financial_expense"] = latest(["Chi phí tài chính"], max_abs=10_000_000_000)
        data["bctt_selling_expense"] = latest(["Chi phí bán hàng"], max_abs=10_000_000_000)
        data["bctt_admin_expense"] = latest(["Chi phí quản lý doanh nghiệp"], max_abs=10_000_000_000)
        data["bctt_net_operating_profit"] = latest(
            ["Lợi nhuận thuần từ hoạt động kinh doanh", "LN thuần từ HĐKD"],
            max_abs=10_000_000_000,
        )
        data["bctt_other_profit"] = latest(["Lợi nhuận khác"], max_abs=10_000_000_000)
        data["bctt_associate_jv_profit"] = latest(
            ["Phần lợi nhuận/lỗ từ công ty liên kết liên doanh", "Phần lợi nhuận từ công ty liên kết liên doanh"],
            max_abs=10_000_000_000,
        )
        data["bctt_profit_before_tax"] = latest(
            ["Tổng lợi nhuận kế toán trước thuế", "Lợi nhuận trước thuế", "LNTT"],
            max_abs=10_000_000_000,
        )
        data["bctt_corporate_income_tax"] = latest(
            ["Chi phí thuế TNDN", "Thuế TNDN", "Thuế thu nhập doanh nghiệp"],
            max_abs=10_000_000_000,
        )
        data["bctt_profit_after_tax"] = latest(
            ["Lợi nhuận sau thuế thu nhập doanh nghiệp", "Lợi nhuận sau thuế", "Tổng LNST"],
            max_abs=10_000_000_000,
        )
        data["bctt_parent_company_profit"] = latest(
            ["Lợi nhuận sau thuế của cổ đông Công ty mẹ", "LNST của CĐ cty mẹ", "LNST của cổ đông công ty mẹ", "LNST của Công ty mẹ"],
            max_abs=10_000_000_000,
        )
        data["bctt_basic_eps"] = latest(["Lãi cơ bản trên cổ phiếu", "EPS cơ bản"], max_abs=10_000_000_000)

        metric_keys = [
            "bctt_net_revenue", "bctt_cost_of_goods_sold", "bctt_gross_profit",
            "bctt_net_operating_profit", "bctt_profit_before_tax", "bctt_profit_after_tax",
            "bctt_parent_company_profit", "bctt_basic_eps",
        ]
        # Nếu BCTT load được nhưng không parse được metric thì để trống, không ghi note lỗi gây nhiễu.

    except Exception as e:
        logging.exception("BCTT crawl failed %s", symbol)
        data["note"] = f"BCTT error: {str(e)[:250]}"

    return data


def crawl_bctt_all_quarters(symbol: str, browser: "VietstockBrowser") -> Dict[str, Dict[str, Any]]:
    """
    Crawl all available quarters from the BCTT tab of Vietstock.
    Returns:
        Dict[str, Dict[str, Any]]: A mapping from period (e.g. "Q1/2026") to a dict of mapped metrics.
    """
    import re
    from bs4 import BeautifulSoup
    from vietstock_crawler.utils.url_utils import make_bctt_url
    from vietstock_crawler.parsers.common import is_error_page
    from vietstock_crawler.utils.number_utils import normalize_number
    from vietstock_crawler.utils.text_utils import normalize_text

    # Define metric mappings
    METRIC_MAPPINGS = {
        "net_revenue": ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "Doanh thu thuần", "Thu nhập lãi thuần"],
        "cost_of_goods_sold": ["Giá vốn hàng bán"],
        "gross_profit": ["Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "Lợi nhuận gộp", "Lãi gộp"],
        "financial_income": ["Doanh thu hoạt động tài chính"],
        "financial_expense": ["Chi phí tài chính"],
        "selling_expense": ["Chi phí bán hàng"],
        "admin_expense": ["Chi phí quản lý doanh nghiệp"],
        "net_profit_from_operating_activity": ["Lợi nhuận thuần từ hoạt động kinh doanh", "LN thuần từ HĐKD", "Lợi nhuận thuần từ HĐKD"],
        "other_profit": ["Lợi nhuận khác"],
        "associate_jv_profit": [
            "Phần lợi nhuận/lỗ từ công ty liên kết liên doanh",
            "Phần lợi nhuận từ công ty liên kết liên doanh",
        ],
        "profit_before_tax": ["Tổng lợi nhuận kế toán trước thuế", "Lợi nhuận trước thuế", "LNTT"],
        "corporate_income_tax": ["Chi phí thuế TNDN", "Thuế TNDN", "Thuế thu nhập doanh nghiệp"],
        "profit_after_tax": ["Lợi nhuận sau thuế thu nhập doanh nghiệp", "Lợi nhuận sau thuế", "Tổng LNST"],
        "parent_company_profit": [
            "Lợi nhuận sau thuế của cổ đông Công ty mẹ",
            "LNST của CĐ cty mẹ",
            "LNST của cổ đông công ty mẹ",
            "LNST của Ngân hàng mẹ",
            "LNST của Công ty mẹ",
        ],
        "eps_4q": [
            "Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)",
            "Lãi cơ bản trên cổ phiếu",
            "EPS cơ bản",
            "EPS 4 quý",
            "EPS",
        ],
        "bvps": ["Giá trị sổ sách của cổ phiếu (BVPS)", "BVPS cơ bản", "BVPS", "Giá trị sổ sách cơ bản trên cổ phiếu"],
        "pe_basic": ["Chỉ số giá thị trường trên thu nhập (P/E)", "P/E cơ bản", "P/E"],
        "pb": ["Chỉ số giá thị trường trên giá trị sổ sách (P/B)", "P/B"],
        "roe": ["Tỷ suất lợi nhuận ròng trên vốn chủ sở hữu (ROE)", "ROE", "Tỷ suất lợi nhuận ròng trên vốn chủ sở hữu"],
        "roa": ["Tỷ suất lợi nhuận ròng trên tài sản (ROA)", "ROA"],
        
        # balance sheet
        "current_assets": ["Tài sản ngắn hạn"],
        "total_assets": ["Tổng tài sản"],
        "customer_loans": ["Cho vay khách hàng"],
        "customer_deposits": ["Tiền gửi của khách hàng", "Tiền gửi của KH"],
        "liabilities": ["Nợ phải trả"],
        "current_liabilities": ["Nợ ngắn hạn"],
        "equity": ["Vốn chủ sở hữu", "Vốn và các quỹ"],
        "retained_earnings": ["Lợi nhuận sau thuế chưa phân phối", "Lợi nhuận chưa phân phối"],
        
        # bank specific
        "net_interest_income": ["Thu nhập lãi thuần"],
        "operating_expense": ["Chi phí hoạt động"],
        "total_operating_income": ["Tổng TNTT", "Tổng thu nhập hoạt động"]
    }

    url = make_bctt_url(symbol)
    periods_data = {}

    try:
        # Load page with BCTT modes (will click Quarter and Bil VND automatically)
        html = browser.get_html(url, use_cache=False, bctt_mode=True)
        if is_error_page(html):
            logging.warning("BCTT URL is invalid: %s", url)
            return {}

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table", class_="table")

        for table_idx, table in enumerate(tables):
            rows = table.find_all("tr")
            if not rows:
                continue

            header_cells = [c.get_text(" ", strip=True) for c in rows[0].find_all(["td", "th"])]
            
            # Identify period columns
            period_cols = {}
            for col_idx, cell_text in enumerate(header_cells):
                cell_text_clean = cell_text.strip()
                if re.search(r"Q\s*[1-4]\s*/\s*20\d{2}", cell_text_clean, re.IGNORECASE):
                    m = re.search(r"Q\s*([1-4])\s*/\s*(20\d{2})", cell_text_clean, re.IGNORECASE)
                    period_cols[col_idx] = f"Q{m.group(1)}/{m.group(2)}"

            if not period_cols:
                continue

            for row in rows[1:]:
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                if not cells:
                    continue

                label = cells[0].strip()
                label_norm = normalize_text(label)

                # Match label
                target_metric = None
                for field, aliases in METRIC_MAPPINGS.items():
                    if any(label_norm == normalize_text(alias) or label_norm.startswith(normalize_text(alias) + " ") for alias in aliases):
                        target_metric = field
                        break

                if not target_metric:
                    continue

                for col_idx, period_name in period_cols.items():
                    if col_idx < len(cells):
                        val_str = cells[col_idx].strip()
                        val = normalize_number(val_str)
                        if val is not None:
                            # Note: BCTT reports in billion VND, while standard DB expects million VND for absolute values.
                            # Standard fields like net_revenue, gross_profit, current_assets, total_assets, liabilities, customer_loans, customer_deposits, equity etc. should be multiplied by 1000 to convert to million VND.
                            # Standard ratios like EPS, P/E, P/B, ROE, ROA, ROS should NOT be multiplied!
                            # Let's see: absolute fields:
                            absolute_fields = {
                                "net_revenue", "cost_of_goods_sold", "gross_profit", "financial_income",
                                "financial_expense", "selling_expense", "admin_expense", "net_profit_from_operating_activity",
                                "other_profit", "associate_jv_profit", "profit_before_tax", "corporate_income_tax",
                                "profit_after_tax", "parent_company_profit", "current_assets", "total_assets",
                                "customer_loans", "customer_deposits", "liabilities", "current_liabilities",
                                "equity", "retained_earnings", "net_interest_income", "operating_expense",
                                "total_operating_income"
                            }
                            
                            if target_metric in absolute_fields:
                                # Multiply by 1000 to convert from Billions to Millions VND
                                val = val * 1000.0

                            if period_name not in periods_data:
                                periods_data[period_name] = {}
                            periods_data[period_name][target_metric] = val

    except Exception as e:
        logging.exception("BCTT parse all quarters failed for %s: %s", symbol, e)

    return periods_data
