from __future__ import annotations

from typing import Any


def build_risk_analysis_prompt(context: dict[str, Any]) -> str:
    """TODO: Lap prompt danh gia rui ro du lieu, rui ro thi truong va rui ro rieng cua co phieu."""
    return "Hãy đánh giá rủi ro bằng JSON tiếng Việt, chỉ dựa trên dữ liệu đầu vào."
