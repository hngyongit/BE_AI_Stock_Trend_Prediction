from __future__ import annotations

import logging
import re
from typing import Any, List

from vietstock_crawler.models.records import empty_trading_stats_record
from vietstock_crawler.parsers.bctt_parser import crawl_bctt_for_trading_stats
from vietstock_crawler.parsers.common import get_line_value_after_label, html_to_lines, is_error_page
from vietstock_crawler.utils.text_utils import clean_config_text, clean_raw_metric_piece, normalize_text
from vietstock_crawler.utils.url_utils import make_stats_url

def force_text_cell(value: Any) -> str:
    """Ép Google Sheets giữ nguyên text, không tự convert sang số/%/date."""
    value = clean_config_text(value)
    if not value:
        return ""
    if value.startswith("'"):
        return value
    return "'" + value


def extract_period_price_change_raw(lines: List[str]) -> tuple[str, str]:
    """
    Không parse/normalize 'Biến động giá'.

    Nếu tách được text hiển thị thành 2 phần thì ghi thẳng raw text vào 2 cột hiện có:
    - Period price change value (VND)
    - Period price change (%)

    Nếu không tách chắc được thì ghi nguyên block đọc được vào cột value và để cột % trống.
    Các giá trị được prefix apostrophe để Google Sheets giữ nguyên text, không tự đổi thành số/%/date.
    """
    label_norm = normalize_text("Biến động giá")
    stop_labels = [
        "Cao nhất", "Thấp nhất", "KLGD/ngày", "KLGD nhiều nhất", "KLGD ít nhất",
        "Giá tham chiếu điều chỉnh", "Giá đóng cửa điều chỉnh",
        "Thống kê theo các tháng", "Thống kê theo các quý", "Thống kê theo các năm",
        "Tổng số phiên", "Tổng KL khớp", "Tổng GT khớp",
    ]
    stop_norms = [normalize_text(x) for x in stop_labels]
    nav_noise = {
        "1 ngay", "5 ngay", "3 thang", "6 thang", "12 thang",
        "tuan", "thang", "quy", "nam", "d", "w", "m", "q", "y",
    }

    for i, line in enumerate(lines):
        norm = normalize_text(line)
        if label_norm not in norm:
            continue

        block_lines: List[str] = []
        for j in range(i, min(len(lines), i + 8)):
            current = clean_config_text(lines[j])
            if not current:
                continue
            current_norm = normalize_text(current)
            if j > i and any(current_norm == s or current_norm.startswith(s + " ") for s in stop_norms):
                break
            if current_norm in nav_noise:
                continue
            block_lines.append(current)
            if "%" in current:
                break

        if not block_lines:
            continue

        raw_block = re.sub(r"\s+", " ", " ".join(block_lines)).strip()
        raw_after_label = re.sub(r"(?i)Biến\s+động\s+giá", "", raw_block, count=1).strip()
        raw_after_label = clean_raw_metric_piece(raw_after_label)

        if not raw_after_label:
            continue

        # Chỉ tách text, không normalize_number. Giữ nguyên dấu phẩy/chấm/dấu %.
        pct_match = re.search(r"[-+−]?\s*\d+(?:[,.]\d+)?\s*%", raw_after_label)
        if pct_match:
            pct_raw = re.sub(r"\s+", "", pct_match.group(0).replace("−", "-"))
            before_pct = raw_after_label[:pct_match.start()]
            value_matches = re.findall(
                r"[-+−]?\s*\d{1,3}(?:[,.]\d{3})+(?:[,.]\d+)?|[-+−]?\s*\d+(?:[,.]\d+)?",
                before_pct,
            )
            value_raw = ""
            if value_matches:
                value_raw = re.sub(r"\s+", "", value_matches[-1].replace("−", "-"))
                # Không nhận các nhiễu điều hướng quá rõ như 1/5 từ tab thời gian.
                if value_raw in ["1", "+1", "-1", "5", "+5", "-5"]:
                    value_raw = ""

            if value_raw:
                return force_text_cell(value_raw), force_text_cell(pct_raw)

            # Có %, nhưng không tách được value: giữ nguyên block vào cột value.
            return force_text_cell(raw_after_label), force_text_cell(pct_raw)

        # Không có %, không cố tách số. Giữ nguyên block đọc được.
        return force_text_cell(raw_after_label), ""

    return "", ""


def crawl_trading_stats(symbol: str, browser: VietstockBrowser, trading_stats_url: str = ""):
    url = make_stats_url(symbol, trading_stats_url)
    data = empty_trading_stats_record(symbol, url)
    try:
        html = browser.get_html(url)
        if is_error_page(html):
            data["error"] = "Invalid URL"
            return data
        lines = html_to_lines(html)
        data["is_valid_url"] = True

        data["price_change_1w_pct"] = get_line_value_after_label(lines, ["+/- Qua 1 tuần"], max_abs=1000, scan_next=3)
        data["price_change_1m_pct"] = get_line_value_after_label(lines, ["+/- Qua 1 tháng"], max_abs=1000, scan_next=3)
        data["price_change_1q_pct"] = get_line_value_after_label(lines, ["+/- Qua 1 quý"], max_abs=1000, scan_next=3)
        data["price_change_1y_pct"] = get_line_value_after_label(lines, ["+/- Qua 1 năm"], max_abs=1000, scan_next=3)
        data["price_change_since_listing_pct"] = get_line_value_after_label(lines, ["+/- Niêm yết"], max_abs=100000, scan_next=3)
        data["high_52w"] = get_line_value_after_label(lines, ["Cao nhất 52 tuần"], min_abs=1000, scan_next=3)
        data["low_52w"] = get_line_value_after_label(lines, ["Thấp nhất 52 tuần"], min_abs=1000, scan_next=3)
        data["avg_volume_day_1w"] = get_line_value_after_label(lines, ["KLGD/Ngày (1 tuần)"], min_abs=1000, scan_next=3)
        data["avg_volume_day_1m"] = get_line_value_after_label(lines, ["KLGD/Ngày (1 tháng)"], min_abs=1000, scan_next=3)
        data["avg_volume_day_1q"] = get_line_value_after_label(lines, ["KLGD/Ngày (1 quý)"], min_abs=1000, scan_next=3)
        data["avg_volume_day_1y"] = get_line_value_after_label(lines, ["KLGD/Ngày (1 năm)"], min_abs=1000, scan_next=3)
        data["max_volume_52w"] = get_line_value_after_label(lines, ["Nhiều nhất 52 tuần"], min_abs=1000, scan_next=3)
        data["min_volume_52w"] = get_line_value_after_label(lines, ["Ít nhất 52 tuần"], min_abs=1000, scan_next=3)
        data["period_reference_adjusted"] = get_line_value_after_label(lines, ["Giá tham chiếu điều chỉnh"], min_abs=1000, scan_next=3)
        data["period_close_adjusted"] = get_line_value_after_label(lines, ["Giá đóng cửa điều chỉnh"], min_abs=1000, scan_next=3)

        # Period price change: parse chặt để không bắt nhầm số 1 từ tab "1 ngày".
        period_change_value, period_change_pct = extract_period_price_change_raw(lines)
        data["period_price_change_value"] = period_change_value
        data["period_price_change_pct"] = period_change_pct

        data["period_high"] = get_line_value_after_label(lines, ["Cao nhất"], min_abs=1000, scan_next=3)
        data["period_low"] = get_line_value_after_label(lines, ["Thấp nhất"], min_abs=1000, scan_next=3)
        data["period_avg_volume_day"] = get_line_value_after_label(lines, ["KLGD/ngày"], min_abs=1000, scan_next=3)
        data["period_max_volume"] = get_line_value_after_label(lines, ["KLGD nhiều nhất"], min_abs=1000, scan_next=3)
        data["period_min_volume"] = get_line_value_after_label(lines, ["KLGD ít nhất"], min_abs=1000, scan_next=3)

        total_sessions, total_volume, total_value, total_bid, total_ask = [], [], [], [], []
        for i, line in enumerate(lines):
            norm = normalize_text(line)
            window = lines[i:i + 4]
            if "tong so phien" in norm:
                v = get_line_value_after_label(window, ["Tổng số phiên"], min_abs=1, max_abs=1000, scan_next=3)
                if v is not None: total_sessions.append(v)
            if "tong kl khop" in norm:
                v = get_line_value_after_label(window, ["Tổng KL khớp"], min_abs=1000, scan_next=3)
                if v is not None: total_volume.append(v)
            if "tong gt khop" in norm:
                v = get_line_value_after_label(window, ["Tổng GT khớp"], min_abs=1, scan_next=3)
                if v is not None: total_value.append(v)
            if "tong kl dat mua" in norm:
                v = get_line_value_after_label(window, ["Tổng KL đặt mua"], min_abs=1000, scan_next=3)
                if v is not None: total_bid.append(v)
            if "tong kl dat ban" in norm:
                v = get_line_value_after_label(window, ["Tổng KL đặt bán"], min_abs=1000, scan_next=3)
                if v is not None: total_ask.append(v)

        groups = [
            (total_sessions, ["month_total_sessions", "quarter_total_sessions", "year_total_sessions"]),
            (total_volume, ["month_total_volume", "quarter_total_volume", "year_total_volume"]),
            (total_value, ["month_total_value", "quarter_total_value", "year_total_value"]),
            (total_bid, ["month_total_bid_volume", "quarter_total_bid_volume", "year_total_bid_volume"]),
            (total_ask, ["month_total_ask_volume", "quarter_total_ask_volume", "year_total_ask_volume"]),
        ]
        for vals, keys in groups:
            for idx, key in enumerate(keys):
                if len(vals) > idx:
                    data[key] = vals[idx]

        # Crawl thêm tab BCTT và merge vào cùng dòng TRADING_STATS.
        bctt_data = crawl_bctt_for_trading_stats(symbol, browser)
        existing_note = data.get("note") or ""
        bctt_note = bctt_data.pop("note", "")
        data.update(bctt_data)

        notes = []
        if existing_note:
            notes.append(existing_note)
        if bctt_note:
            notes.append(bctt_note)

        # Nếu không parse được trading stats thì để trống, không ghi note lỗi gây nhiễu.
        data["note"] = "; ".join(notes)

    except Exception as e:
        logging.exception("Trading stats failed %s", symbol)
        data["error"] = str(e)
    return data
