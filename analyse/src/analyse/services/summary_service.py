from __future__ import annotations

from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.schemas.common import DEFAULT_DISCLAIMER
from analyse.schemas.research import ExternalResearchContext
from analyse.services.scoring_service import ScoringService
from analyse.services.stock_data_service import StockDataService
from analyse.utils.symbol_utils import normalize_symbol


class SummaryService:
    """Tạo summary lõi từ payload Backend analysis-data đã chuẩn hóa."""

    def __init__(
        self,
        stock_data_service: StockDataService | None = None,
        scoring_service: ScoringService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
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
        normalized = self.stock_data_service.normalize_analysis_data(stock_detail)
        symbol = normalize_symbol(normalized.get("symbol") or symbol)
        latest_market = self._dict(normalized.get("latest_market"))
        price_history = self._list(normalized.get("price_history"))
        financials = self._dict(normalized.get("financials"))
        financial_periods = self._list(financials.get("periods"))
        financial_balance = self._dict(normalized.get("financial_balance"))
        data_quality = self._dict(normalized.get("data_quality"))
        source_success = self._dict(normalized.get("_source_success"))
        company = normalized.get("company") or self.stock_data_service.extract_company(stock_detail)
        data_quality_notes = self._build_data_quality_notes(data_quality, financial_periods, warnings)
        hose_market_context = self._dict(normalized.get("hose_market_context"))
        industry_peer_context = self._dict(normalized.get("industry_peer_context"))
        peers = self._list(industry_peer_context.get("peers"))
        analysis_data_loaded = self._source_loaded(
            source_success,
            "analysis_data_loaded",
            fallback=self._looks_like_analysis_data(normalized),
        )
        backend_stock_detail_loaded = self._source_loaded(
            source_success,
            "backend_stock_detail_loaded",
            fallback=bool(stock_detail),
        )

        scoring_input = {
            **normalized,
            "latest_market": latest_market,
            "price_history": price_history,
            "financials": {"periods": financial_periods},
            "hose_market_context": hose_market_context,
        }
        if self.settings.enable_scoring:
            scores = self.scoring_service.build_scores(scoring_input)
        else:
            scores = self._disabled_scores()
            data_quality_notes.append("Scoring đang tắt bởi ENABLE_SCORING=false.")

        summary = {
            "symbol": symbol,
            "company": company,
            "scope_exchange": scope_exchange or normalized.get("exchange") or "HOSE",
            "disclaimer": DEFAULT_DISCLAIMER,
            "data_coverage": {
                "backend_stock_detail_loaded": backend_stock_detail_loaded,
                "analysis_data_loaded": analysis_data_loaded,
                "latest_price_loaded": self._has_latest_price(latest_market),
                "financials_loaded": bool(financial_periods),
                "financial_periods_count": len(financial_periods),
                "price_history_points": len(price_history),
                "market_context_loaded": self._has_market_context(hose_market_context),
                "peer_context_loaded": bool(peers),
                "external_research_items": len(research_context.items) if research_context else 0,
            },
            "latest_market": latest_market,
            "momentum": self._build_momentum(price_history),
            "bctc_3q": {
                "has_bctc": bool(financial_periods),
                "periods": financial_periods[:3],
                "total_periods_available": len(financial_periods),
                "data_quality_notes": data_quality_notes,
            },
            "financial_balance": financial_balance,
            "hose_market_context": hose_market_context,
            "industry_peer_context": industry_peer_context,
            "market_general_context": self._dict(normalized.get("market_general_context")),
            "same_industry_recommendation": self._dict(normalized.get("same_industry_recommendation")),
            "data_quality": data_quality,
            "data_quality_notes": data_quality_notes,
            "scores": scores,
            "score_explanations": self._string_list(scores.get("score_explanations")),
            "strengths": self._default_strengths(latest_market, financial_periods, scores),
            "weaknesses": self._default_weaknesses(data_quality, scores),
            "external_research_context": research_context.model_dump() if research_context else {"enabled": False, "status": "disabled", "items": []},
            "system_decision": self._build_system_decision(scores, data_quality, bool(financial_periods), hose_market_context),
            "investment_plan": {"decision": {}, "reference_levels": {}, "position_sizing": {}, "action_table": []},
            "warnings": self._dedupe([*(warnings or []), *self._string_list(data_quality.get("warnings"))]),
        }
        return summary

    def _source_loaded(self, source_success: dict[str, Any], key: str, *, fallback: bool) -> bool:
        if key in source_success:
            return bool(source_success.get(key))
        return fallback

    def _looks_like_analysis_data(self, normalized: dict[str, Any]) -> bool:
        raw = self._dict(normalized.get("raw"))
        return any(
            key in raw
            for key in (
                "latestMarket",
                "latest_market",
                "priceHistory",
                "price_history",
                "financials",
                "dataQuality",
                "data_quality",
                "hoseMarketContext",
                "industryPeerContext",
            )
        )

    def _has_latest_price(self, latest_market: dict[str, Any]) -> bool:
        return any(
            isinstance(latest_market.get(key), (int, float))
            for key in ("close_price", "close", "last_price", "price", "open_price", "volume")
        )

    def _has_market_context(self, market_context: dict[str, Any]) -> bool:
        return any(
            market_context.get(key) not in (None, "", {}, [])
            for key in ("vnindex", "change", "change_percent", "total_volume", "total_value", "regime", "foreign_net")
        )

    def _build_momentum(self, price_history: Any) -> dict[str, Any]:
        if not isinstance(price_history, list) or len(price_history) < 2:
            return {}

        closes: list[float] = []
        for item in price_history:
            if not isinstance(item, dict):
                continue
            close = item.get("close") or item.get("close_price")
            if isinstance(close, (int, float)):
                closes.append(float(close))

        if len(closes) < 2 or closes[0] == 0:
            return {}

        change_pct = round(((closes[-1] - closes[0]) / closes[0]) * 100, 2)
        return {
            "period_points": len(closes),
            "first_close": closes[0],
            "last_close": closes[-1],
            "change_pct": change_pct,
        }

    def _build_data_quality_notes(self, data_quality: dict[str, Any], periods: list[dict[str, Any]], warnings: list[str] | None) -> list[str]:
        notes: list[str] = []
        if not periods:
            notes.append("Chưa có financials/BCTC đầy đủ trong payload.")
        missing_fields = self._string_list(data_quality.get("missing_fields"))
        if missing_fields:
            notes.append("Field thiếu từ Backend: " + ", ".join(missing_fields))
        notes.extend(self._string_list(data_quality.get("warnings")))
        notes.extend(warnings or [])
        return self._dedupe(notes)

    def _build_system_decision(
        self,
        scores: dict[str, Any],
        data_quality: dict[str, Any],
        has_financials: bool,
        market_context: dict[str, Any],
    ) -> dict[str, Any]:
        overall = scores.get("overall_score")
        risk = scores.get("risk_score")
        confidence = scores.get("score_confidence") or 0
        regime = str(market_context.get("regime") or "").lower()
        missing_fields = self._string_list(data_quality.get("missing_fields"))

        status = "CÓ THỂ THEO DÕI"
        action = "Theo dõi thêm và chỉ đánh giá vị thế sau khi đối chiếu dữ liệu gốc."
        reasons = []
        blockers = []

        if not has_financials and confidence < 0.6:
            status = "CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN"
            action = "Chưa nên ra quyết định theo dữ liệu hiện tại; cần bổ sung BCTC và kiểm chứng nguồn."
            blockers.append("Thiếu BCTC đủ kỳ để đánh giá chất lượng và tăng trưởng.")
        elif isinstance(risk, (int, float)) and risk >= 75:
            status = "RỦI RO CAO, CẦN THẬN TRỌNG"
            action = "Ưu tiên quản trị rủi ro và chờ tín hiệu xác nhận tốt hơn."
        elif isinstance(overall, (int, float)) and overall >= 75 and (not isinstance(risk, (int, float)) or risk < 60) and regime != "risk_off":
            status = "TÍN HIỆU TÍCH CỰC CÓ ĐIỀU KIỆN"
            action = "Có thể đưa vào danh sách theo dõi ưu tiên nếu dữ liệu gốc và khẩu vị rủi ro phù hợp."
        elif isinstance(overall, (int, float)) and overall < 40:
            status = "KHÔNG PHÙ HỢP ĐỂ MỞ VỊ THẾ MỚI THEO DỮ LIỆU HIỆN TẠI"
            action = "Chỉ theo dõi, chưa đủ hấp dẫn theo bộ chỉ báo hiện tại."

        if regime == "risk_off":
            reasons.append("Market context đang risk_off nên cần hạ mức tự tin của tín hiệu.")
        if isinstance(overall, (int, float)):
            reasons.append(f"Overall score hiện tại là {overall}/100, nhãn {scores.get('overall_label')}.")
        if isinstance(risk, (int, float)):
            reasons.append(f"Risk score là {risk}/100, nhãn rủi ro {scores.get('risk_label')}.")
        if missing_fields:
            blockers.append("Backend còn thiếu: " + ", ".join(missing_fields))

        return {
            "status": status,
            "action": action,
            "reasons": reasons or ["Cần kiểm tra thêm vì dữ liệu định lượng còn hạn chế."],
            "blockers": blockers,
            "confidence": confidence,
            "note": DEFAULT_DISCLAIMER,
        }

    def _default_strengths(self, latest_market: dict[str, Any], periods: list[dict[str, Any]], scores: dict[str, Any]) -> list[str]:
        strengths: list[str] = []
        if latest_market:
            strengths.append("Backend đã cung cấp dữ liệu thị trường mới nhất.")
        if periods:
            strengths.append(f"Backend đã cung cấp {len(periods)} kỳ BCTC để phân tích.")
        if isinstance(scores.get("overall_score"), int):
            strengths.append("Service đã tính được dashboard scoring định lượng.")
        return strengths

    def _default_weaknesses(self, data_quality: dict[str, Any], scores: dict[str, Any]) -> list[str]:
        weaknesses = self._string_list(data_quality.get("warnings"))
        missing = self._string_list(data_quality.get("missing_fields"))
        if missing:
            weaknesses.append("Một số field Backend còn thiếu: " + ", ".join(missing))
        if (scores.get("score_confidence") or 0) < 0.6:
            weaknesses.append("Độ tin cậy scoring còn thấp do dữ liệu đầu vào chưa đầy đủ.")
        return weaknesses or ["Cần tiếp tục kiểm chứng dữ liệu gốc trước khi sử dụng báo cáo."]

    def _disabled_scores(self) -> dict[str, Any]:
        return {
            "valuation_score": None,
            "quality_score": None,
            "growth_score": None,
            "momentum_score": None,
            "liquidity_score": None,
            "size_score": None,
            "risk_score": None,
            "risk_label": "Chưa tính",
            "overall_score": None,
            "overall_label": "Chưa tính",
            "score_confidence": 0,
            "score_explanations": ["Scoring đang tắt bởi cấu hình."],
        }

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _dedupe(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = str(value).strip()
            if clean and clean not in seen:
                result.append(clean)
                seen.add(clean)
        return result
