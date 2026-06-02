from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from vietstock_crawler.parsers.common import find_value_in_short_window, get_line_value_after_label
from vietstock_crawler.utils.number_utils import normalize_number, sanitize_share_volume
from vietstock_crawler.utils.text_utils import clean_config_text, merge_notes, normalize_text

def extract_foreign_volume(html: str, lines: List[str], text: str, labels: List[str]) -> Optional[float]:
    """
    Parser riêng cho NN mua/NN bán.
    Nếu không chắc thì để trống, không ghi sai các số nhỏ như 27.
    """
    value = find_value_in_short_window(text, labels, min_abs=1000, max_abs=10_000_000_000, window_chars=140)
    value = sanitize_share_volume(value)
    if value is not None:
        return value

    value = get_line_value_after_label(
        lines,
        labels,
        min_abs=1000,
        max_abs=10_000_000_000,
        mode="first",
        scan_next=6,
    )
    return sanitize_share_volume(value)


def extract_current_price(lines: List[str], text: str) -> Optional[float]:
    """
    Lấy GIÁ HIỆN TẠI trong block giá lớn của trang profile Vietstock.

    Quy tắc an toàn:
    - Không lấy số tăng/giảm như 1,700 / 10,300.
    - Không lấy số % hoặc ngày giờ.
    - Ưu tiên dòng giá đứng trước dòng trạng thái "Kết thúc phiên" / "Đang giao dịch".
    - Nếu không chắc thì trả None để tránh ghi bừa.
    """

    status_keywords = [
        "ket thuc phien",
        "dang giao dich",
        "tam ngung giao dich",
        "ngung giao dich",
        "dung giao dich",
    ]

    def valid_price_tokens(raw: str) -> List[float]:
        raw = clean_config_text(raw)
        if not raw:
            return []

        # Bỏ qua các dòng chắc chắn không phải giá hiện tại.
        raw_norm = normalize_text(raw)
        if "%" in raw:
            return []
        if re.search(r"\d{1,2}/\d{1,2}/20\d{2}", raw):
            return []
        if re.search(r"\b\d{1,2}:\d{2}\b", raw):
            return []
        if any(label in raw_norm for label in [
            "mo cua", "cao nhat", "thap nhat", "klgd", "von hoa", "du mua", "du ban",
            "nn mua", "nn ban", "eps", "p/e", "bvps", "beta", "p/b", "cao 52t", "thap 52t",
        ]):
            return []

        # Chỉ nhận dạng giá có phân tách nghìn: 93,500 / 93.500 / 1,550.
        tokens = re.findall(r"(?<![\d/])[-+]?\d{1,3}(?:[,.]\d{3})+(?![\d/%])", raw)
        values: List[float] = []
        for token in tokens:
            value = normalize_number(token)
            if value is None:
                continue
            if 1000 <= abs(value) <= 1_000_000:
                values.append(value)
        return values

    # 1) Ưu tiên block dòng ngay trước trạng thái phiên.
    # Thứ tự thường là: Giá hiện tại -> mức tăng/giảm (%) -> ngày giờ -> Kết thúc phiên.
    # Vì vậy phải lấy DÒNG GIÁ ĐẦU TIÊN hợp lệ trong block, không lấy số cuối.
    for i, line in enumerate(lines):
        norm = normalize_text(line)
        if any(keyword in norm for keyword in status_keywords):
            block_lines = lines[max(0, i - 10):i]
            for block_line in block_lines:
                candidates = valid_price_tokens(block_line)
                if candidates:
                    # Nếu một dòng có nhiều token thì ưu tiên token đầu, vì dòng giá lớn thường chỉ có một số.
                    return candidates[0]

    # 2) Fallback raw text: tìm đoạn trước status theo text gốc rồi lấy dòng/token giá hợp lệ đầu tiên.
    compact = re.sub(r"\s+", " ", text or " ").strip()
    raw_status_patterns = [
        "Kết thúc phiên", "Đang giao dịch", "Tạm ngưng giao dịch", "Ngưng giao dịch", "Dừng giao dịch",
    ]
    status_positions = []
    compact_lower = compact.lower()
    for status in raw_status_patterns:
        pos = compact_lower.find(status.lower())
        if pos >= 0:
            status_positions.append(pos)

    if status_positions:
        pos = min(status_positions)
        window = compact[max(0, pos - 350):pos]

        # Cắt theo các cụm có vẻ là dòng. Dòng tăng/giảm thường chứa %, nên bị bỏ.
        parts = re.split(r"(?<=\))\s+|(?<=%)\s+|\s{2,}", window)
        for part in parts:
            candidates = valid_price_tokens(part)
            if candidates:
                return candidates[0]

        # Fallback cuối: trong cửa sổ trước status, chọn token hợp lệ đầu tiên mà không nằm cạnh %.
        candidates = valid_price_tokens(window)
        if candidates:
            return candidates[0]

    return None


def validate_market_price(record: Dict[str, Any]) -> None:
    """
    Kiểm tra nhẹ để tránh ghi giá hiện tại bị lệch quá xa so với High/Low.
    Không tự chế giá thay thế. Nếu nghi sai thì để trống và ghi note.
    """
    price = record.get("price")
    high = record.get("high")
    low = record.get("low")
    if price is None or high is None or low is None:
        return
    try:
        price_f = float(price)
        high_f = float(high)
        low_f = float(low)
    except Exception:
        return
    if high_f <= 0 or low_f <= 0:
        return
    lower_bound = low_f * 0.85
    upper_bound = high_f * 1.15
    if not (lower_bound <= price_f <= upper_bound):
        note = clean_config_text(record.get("note"))
        extra = f"Price rejected outside High/Low range: {price_f:g}"
        record["price"] = None
        record["close"] = None
        record["note"] = merge_notes(note, extra) if "merge_notes" in globals() else extra
