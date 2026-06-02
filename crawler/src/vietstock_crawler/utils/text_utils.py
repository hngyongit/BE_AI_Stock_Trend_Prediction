from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

import pandas as pd


def strip_accents(value: str) -> str:
    value = str(value)
    normalized = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "D")
    return value


def normalize_text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = strip_accents(value).lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^a-z0-9%/+.\- ]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def clean_config_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    value = str(value).strip()
    return "" if value.lower() in ["nan", "none", "null"] else value


def clean_cell_value(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def merge_notes(*items: str) -> str:
    notes = []
    for item in items:
        item = clean_config_text(item)
        if item and item not in notes:
            notes.append(item)
    return "; ".join(notes)


def clean_raw_metric_piece(value: str) -> str:
    value = clean_config_text(value)
    value = re.sub(r"^\s*[:\-–—]+\s*", "", value)
    value = value.strip(" ()[]")
    return value.strip()
