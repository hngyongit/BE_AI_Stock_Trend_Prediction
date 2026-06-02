from __future__ import annotations

import re
from typing import Any, Optional, List

from vietstock_crawler.utils.text_utils import clean_config_text


def normalize_number(value: Any) -> Optional[float]:
    if value is None:
        return None

    s = str(value).strip()
    if s in ["", "-", "—", "nan", "None", "NaN"]:
        return None

    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1]
    if s.startswith("-"):
        is_negative = True

    s = s.replace("%", "").replace("cp", "").replace("VND", "").replace("vnd", "")
    s = s.replace("tỷ đồng", "").replace("triệu", "").replace(" ", " ").strip()
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None

    if "," in s and "." in s:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 3:
            s = s.replace(",", "")
        elif len(parts[-1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            s = s.replace(".", "")
        elif len(parts[-1]) == 3 and len(parts[0]) <= 3:
            s = s.replace(".", "")

    try:
        num = float(s)
        return -abs(num) if is_negative else num
    except ValueError:
        return None


def numbers_from_text(text: str, skip_years: bool = True) -> List[float]:
    tokens = re.findall(r"\(?[-+]?\d[\d,.]*%?\)?", text)
    nums = []
    for token in tokens:
        num = normalize_number(token)
        if num is None:
            continue
        if skip_years and 1900 <= abs(num) <= 2100 and re.fullmatch(r"\(?[-+]?\d{4}\)?", token.strip()):
            continue
        nums.append(num)
    return nums


def sanitize_share_volume(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if v == 0:
        return 0
    if 0 < abs(v) < 1000:
        return None
    return v
