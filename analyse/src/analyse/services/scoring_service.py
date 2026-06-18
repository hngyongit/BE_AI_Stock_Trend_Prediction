from __future__ import annotations

from typing import Any


class ScoringService:
    """Tính điểm định lượng bằng code. Hiện là placeholder an toàn."""

    def build_placeholder_scores(self, stock_detail: dict[str, Any]) -> dict[str, Any]:
        return {
            "valuation_score": None,
            "quality_score": None,
            "growth_score": None,
            "momentum_score": None,
            "liquidity_score": None,
            "size_score": None,
            "risk_score": None,
            "risk_label": "Chưa đủ dữ liệu",
            "overall_score": None,
            "overall_label": "Chưa đủ dữ liệu",
        }
