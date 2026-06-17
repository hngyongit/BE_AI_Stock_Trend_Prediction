from __future__ import annotations

from typing import Any


def build_watchlist_analysis_prompt(stocks: list[dict[str, Any]], options: dict[str, Any]) -> str:
    """TODO: Lap prompt so sanh watchlist theo rui ro, co hoi va diem can theo doi."""
    return (
        "Hãy tạo phân tích JSON bằng tiếng Việt cho watchlist được cung cấp. "
        "Đây mới là template skeleton; chưa có logic xếp hạng thật."
    )
