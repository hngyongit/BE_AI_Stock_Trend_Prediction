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
