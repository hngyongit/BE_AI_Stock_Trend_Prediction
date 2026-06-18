from __future__ import annotations

import json
from typing import Any


def safe_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def safe_json_loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON không hợp lệ: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON root phải là object.")
    return value
