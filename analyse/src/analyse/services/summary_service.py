from __future__ import annotations

from typing import Any

from analyse.schemas.common import DEFAULT_DISCLAIMER
from analyse.schemas.research import ExternalResearchContext
from analyse.services.scoring_service import ScoringService
from analyse.services.stock_data_service import StockDataService
from analyse.utils.symbol_utils import normalize_symbol


class SummaryService:
    """Tạo summary lõi để frontend render HTML/Markdown."""

    def __init__(self, stock_data_service: StockDataService | None = None, scoring_service: ScoringService | None = None) -> None:
        self.stock_data_service = stock_data_service or StockDataService()
        self.scoring_service = scoring_service or ScoringService()

    def build_summary(
        self,
        *,
        symbol: str,
        stock_detail: dict[str, Any],
        research_context: ExternalResearchContext | None = None,
        scope_exchange: str = "HOSE",
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        symbol = normalize_symbol(symbol)
        latest_price = stock_detail.get("latest_price") or stock_detail.get("latestPrice") or {}
        financials = stock_detail.get("financials") or {}
        company = self.stock_data_service.extract_company(stock_detail)

        return {
            "symbol": symbol,
            "company": company,
            "scope_exchange": scope_exchange,
            "disclaimer": DEFAULT_DISCLAIMER,
            "data_coverage": {
                "backend_stock_detail_loaded": bool(stock_detail),
                "latest_price_loaded": bool(latest_price),
                "financials_loaded": bool(financials),
                "external_research_items": len(research_context.items) if research_context else 0,
            },
            "latest_market": latest_price,
            "momentum": {},
            "bctc_3q": {
                "has_bctc": bool(financials),
                "periods": financials if isinstance(financials, list) else [],
                "data_quality_notes": [] if financials else ["Chưa có financials/BCTC đầy đủ trong payload."],
            },
            "financial_balance": financials if isinstance(financials, dict) else {},
            "hose_market_context": stock_detail.get("market_overview") or stock_detail.get("marketOverview") or {},
            "scores": self.scoring_service.build_placeholder_scores(stock_detail),
            "strengths": [],
            "weaknesses": ["Summary hiện là scaffold; cần triển khai tính toán định lượng chi tiết."],
            "industry_peer_context": {},
            "market_general_context": {},
            "same_industry_recommendation": {},
            "external_research_context": research_context.model_dump() if research_context else {"enabled": False, "status": "disabled", "items": []},
            "system_decision": {
                "status": "CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN",
                "action": "Chỉ dùng để kiểm thử luồng dữ liệu; chưa phải tín hiệu đầu tư.",
                "reasons": ["Service đang ở trạng thái scaffold."],
                "blockers": [],
                "note": DEFAULT_DISCLAIMER,
            },
            "investment_plan": {"decision": {}, "reference_levels": {}, "position_sizing": {}, "action_table": []},
            "warnings": warnings or [],
        }
