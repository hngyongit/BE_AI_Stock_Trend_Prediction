from __future__ import annotations

import logging
from typing import Any, Dict

from vietstock_crawler.parsers.bctt_parser import crawl_bctt_for_trading_stats

def apply_bctt_fallback_to_financial(symbol: str, browser: "VietstockBrowser", financial: Dict[str, Any]) -> None:
    """
    Bù dữ liệu FINANCIAL_DATA từ tab BCTT nếu profile chính thiếu.
    BCTT trả đơn vị Tỷ đồng, còn FINANCIAL_DATA dùng mil VND => nhân 1,000.
    """
    try:
        need_bctt = not any([
            financial.get("net_revenue"),
            financial.get("gross_profit"),
            financial.get("net_profit_from_operating_activity"),
            financial.get("profit_before_tax"),
            financial.get("profit_after_tax"),
            financial.get("parent_company_profit"),
        ])

        # Nếu vẫn có một vài dòng trống quan trọng thì cũng nên bù, nhưng không bắt buộc.
        important_missing = any(financial.get(k) in [None, ""] for k in [
            "net_revenue", "gross_profit", "net_profit_from_operating_activity",
            "profit_before_tax", "profit_after_tax", "parent_company_profit",
        ])

        if not (need_bctt or important_missing):
            return

        bctt = crawl_bctt_for_trading_stats(symbol, browser)

        def fill_mil(target: str, source: str):
            val = bctt.get(source)
            if financial.get(target) in [None, ""] and val is not None:
                financial[target] = val * 1000

        fill_mil("net_revenue", "bctt_net_revenue")
        fill_mil("gross_profit", "bctt_gross_profit")
        fill_mil("net_profit_from_operating_activity", "bctt_net_operating_profit")
        fill_mil("corporate_income_tax", "bctt_corporate_income_tax")
        fill_mil("profit_before_tax", "bctt_profit_before_tax")
        fill_mil("profit_after_tax", "bctt_profit_after_tax")
        fill_mil("parent_company_profit", "bctt_parent_company_profit")

        # EPS BCTT đã là VND/share, không nhân 1000.
        if financial.get("eps_4q") in [None, ""] and bctt.get("bctt_basic_eps") is not None:
            financial["eps_4q"] = bctt.get("bctt_basic_eps")

    except Exception as e:
        # Không fail toàn bộ mã chỉ vì fallback BCTT lỗi.
        logging.warning("Financial BCTT fallback failed %s: %s", symbol, str(e)[:250])
