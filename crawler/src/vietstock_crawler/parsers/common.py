from __future__ import annotations

import re
from typing import Any, List, Optional

from bs4 import BeautifulSoup

from vietstock_crawler.config.settings import ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET
from vietstock_crawler.utils.date_utils import latest_completed_quarter_suffix, parse_quarter_suffix, quarter_sort_key, is_quarter_after
from vietstock_crawler.utils.number_utils import normalize_number, numbers_from_text
from vietstock_crawler.utils.text_utils import clean_config_text, normalize_text

def is_error_page(html: str) -> bool:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
    signals = [
        "đường dẫn không tồn tại",
        "vui lòng kiểm tra lại đường dẫn",
        "vietstockfinance > index",
        "/error/index",
    ]
    return any(signal in text for signal in signals)


def html_to_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def is_noise_number_line(line: str) -> bool:
    norm = normalize_text(line)
    if re.search(r"\bq(u|uy|uý)?\s*\d[/\s-]*20\d{2}\b", norm):
        return True
    if re.search(r"\d{1,2}/\d{1,2}/20\d{2}", line):
        return True
    if "ckt/hn" in norm or "ck t/hn" in norm:
        return True
    if norm.startswith("nam 20") or norm.startswith("năm 20"):
        return True
    return False


def get_line_value_after_label(
    lines: List[str],
    labels: List[str],
    min_abs: Optional[float] = None,
    max_abs: Optional[float] = None,
    mode: str = "first",
    scan_next: int = 8,
    skip_years: bool = True,
) -> Optional[float]:
    label_norms = [normalize_text(x) for x in labels]
    best_idx = None

    for i, line in enumerate(lines):
        norm = normalize_text(line)
        if any(norm == lb or norm.startswith(lb + " ") for lb in label_norms):
            best_idx = i
            break
    if best_idx is None:
        for i, line in enumerate(lines):
            norm = normalize_text(line)
            if any(lb in norm for lb in label_norms):
                best_idx = i
                break
    if best_idx is None:
        return None

    candidates = []
    for offset in range(scan_next + 1):
        pos = best_idx + offset
        if pos >= len(lines):
            break
        line = lines[pos]
        if is_noise_number_line(line):
            continue

        if offset == 0:
            norm = normalize_text(line)
            cut_line = line
            for raw_label, label_norm in zip(labels, label_norms):
                if norm == label_norm:
                    cut_line = ""
                    break
                if norm.startswith(label_norm):
                    cut_line = re.sub(re.escape(raw_label), "", line, count=1, flags=re.IGNORECASE)
                    break
            nums = numbers_from_text(cut_line, skip_years=skip_years)
        else:
            nums = numbers_from_text(line, skip_years=skip_years)

        for num in nums:
            if min_abs is not None and abs(num) < min_abs:
                continue
            if max_abs is not None and abs(num) > max_abs:
                continue
            candidates.append(num)

        # Với mode="first" thì trả ngay để nhanh.
        # Với mode="last" phải quét hết vùng scan_next rồi mới lấy số cuối cùng,
        # tránh lấy nhầm cột quý cũ hoặc số nằm ở dòng kế bên.
        if candidates and mode != "last":
            return candidates[0]

    if not candidates:
        return None

    return candidates[-1] if mode == "last" else candidates[0]


def get_latest_metric_from_tables(
    html: str,
    labels: List[str],
    min_abs: Optional[float] = None,
    max_abs: Optional[float] = None,
) -> Optional[float]:
    """
    Lấy giá trị mới nhất của một dòng metric trong bảng HTML Vietstock.

    Ví dụ bảng tài chính hiển thị các cột cũ -> mới:
    Quý 2/2025 | Quý 3/2025 | Quý 4/2025 | Quý 1/2026
    Hàm này lấy số cuối cùng trong đúng dòng metric, không quét lan sang dòng khác.
    Nhờ vậy tránh lỗi ROEA/ROAA/ROE bị lệch như lấy ROAA = 25 từ ngày/thời gian.
    """
    label_norms = [normalize_text(label) for label in labels]

    try:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")

        for tr in rows:
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]

            if len(cells) < 2:
                continue

            first_norm = normalize_text(cells[0])

            is_match = any(
                first_norm == label_norm
                or first_norm.startswith(label_norm + " ")
                or label_norm in first_norm
                for label_norm in label_norms
            )

            if not is_match:
                continue

            candidates = []
            for cell_text in cells[1:]:
                if is_noise_number_line(cell_text):
                    continue

                for num in numbers_from_text(cell_text, skip_years=True):
                    if min_abs is not None and abs(num) < min_abs:
                        continue
                    if max_abs is not None and abs(num) > max_abs:
                        continue
                    candidates.append(num)

            if candidates:
                return candidates[-1]

    except Exception:
        return None

    return None


def get_latest_metric_value(
    html: str,
    lines: List[str],
    labels: List[str],
    min_abs: Optional[float] = None,
    max_abs: Optional[float] = None,
    scan_next: int = 12,
) -> Optional[float]:
    """
    Ưu tiên đọc đúng hàng trong table; nếu không có table thì fallback sang text parser.
    """
    value = get_latest_metric_from_tables(
        html=html,
        labels=labels,
        min_abs=min_abs,
        max_abs=max_abs,
    )

    if value is not None:
        return value

    return get_line_value_after_label(
        lines,
        labels,
        min_abs=min_abs,
        max_abs=max_abs,
        mode="last",
        scan_next=scan_next,
    )


def extract_latest_period_label(html: str) -> str:
    """
    Lấy nhãn kỳ báo cáo mới nhất, mặc định không vượt quá quý đã kết thúc.
    Tránh bị nhảy sang Q2 khi mới đang trong Q2 nhưng BCTC hoàn chỉnh mới là Q1.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = html or ""

    suffixes: List[str] = []
    patterns = [
        r"Q\s*([1-4])\s*/\s*(20\d{2})",
        r"Quý\s*([1-4])\s*/\s*(20\d{2})",
        r"Quí\s*([1-4])\s*/\s*(20\d{2})",
        r"Qui\s*([1-4])\s*/\s*(20\d{2})",
    ]
    for pattern in patterns:
        for q, y in re.findall(pattern, text, flags=re.IGNORECASE):
            suffix = parse_quarter_suffix(f"Q{q}_{y}")
            if suffix:
                suffixes.append(suffix)

    if not suffixes:
        return ""

    max_allowed = latest_completed_quarter_suffix()
    if not ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET:
        suffixes = [suf for suf in suffixes if not is_quarter_after(suf, max_allowed)]

    if not suffixes:
        suffix = max_allowed
    else:
        suffix = max(suffixes, key=quarter_sort_key)

    m = re.fullmatch(r"Q([1-4])_(20\d{2})", suffix)
    return f"Q{m.group(1)}/{m.group(2)}" if m else suffix


def get_line_values_after_label(
    lines: List[str],
    labels: List[str],
    min_abs: Optional[float] = None,
    max_abs: Optional[float] = None,
    scan_next: int = 8,
    skip_years: bool = True,
) -> List[float]:
    values = []
    for label in labels:
        val = get_line_value_after_label(lines, [label], min_abs, max_abs, "first", scan_next, skip_years)
        if val is not None:
            values.append(val)
    if values:
        return values

    label_norms = [normalize_text(x) for x in labels]
    best_idx = None
    for i, line in enumerate(lines):
        norm = normalize_text(line)
        if any(lb in norm for lb in label_norms):
            best_idx = i
            break
    if best_idx is None:
        return []
    for offset in range(scan_next + 1):
        pos = best_idx + offset
        if pos >= len(lines):
            break
        if is_noise_number_line(lines[pos]):
            continue
        for num in numbers_from_text(lines[pos], skip_years=skip_years):
            if min_abs is not None and abs(num) < min_abs:
                continue
            if max_abs is not None and abs(num) > max_abs:
                continue
            values.append(num)
    return values


def find_value_in_text_near_label(text: str, label: str) -> Optional[float]:
    """
    Lấy số ngay sau label trong vùng ngắn, tránh regex quét quá xa.
    Ví dụ: P/E không được bắt nhầm F P/E, NN bán không được bắt nhầm ngày.
    """
    compact = re.sub(r"\s+", " ", text or " ").strip()
    label_patterns = [re.escape(label)]

    # Với các label dễ đè nhau, thêm ranh giới phía trước.
    for pattern in label_patterns:
        m = re.search(rf"(?<![A-Za-zÀ-ỹ/]){pattern}\s*[:\-]?\s*([()]?[-+]?\d[\d,.]*%?[)]?)", compact, flags=re.IGNORECASE)
        if m:
            return normalize_number(m.group(1))

    return None


def find_value_in_short_window(text: str, labels: List[str], min_abs: Optional[float] = None, max_abs: Optional[float] = None, window_chars: int = 100) -> Optional[float]:
    compact = re.sub(r"\s+", " ", text or " ").strip()
    low = compact.lower()
    for label in labels:
        pos = low.find(label.lower())
        if pos < 0:
            continue
        seg = compact[pos + len(label): pos + len(label) + window_chars]
        nums = numbers_from_text(seg, skip_years=True)
        for n in nums:
            if min_abs is not None and abs(n) < min_abs:
                continue
            if max_abs is not None and abs(n) > max_abs:
                continue
            return n
    return None
