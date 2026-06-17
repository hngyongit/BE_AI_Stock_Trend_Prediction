from __future__ import annotations

from typing import Any


def parse_optional_float(value: Any) -> float | None:
    """TODO: Mo rong de xu ly dinh dang so Viet Nam, dau phay, percent va gia tri rong."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
