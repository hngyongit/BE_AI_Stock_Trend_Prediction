from __future__ import annotations

from typing import Any


def build_stock_analysis_prompt(symbol: str, data: dict[str, Any], options: dict[str, Any]) -> str:
    """TODO: Lap prompt phan tich mot ma co phieu tu du lieu backend da chuan hoa."""
    return (
        f"Hãy tạo phân tích JSON bằng tiếng Việt cho mã {symbol.upper()}. "
        "Đây mới là template skeleton; cần bổ sung logic nén dữ liệu và schema sau."
    )
