from __future__ import annotations

import re
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.schemas.common import DEFAULT_DISCLAIMER
from analyse.schemas.research import ExternalResearchContext
from analyse.services.presentation_contract import display_percent_value
from analyse.services.presentation_contract import normalize_percent_score
from analyse.services.presentation_contract import normalize_score_0_100
from analyse.services.scoring_service import ScoringService
from analyse.services.stock_data_service import StockDataService
from analyse.utils.datetime_utils import format_datetime_vi
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
        raw_financial_periods = self._list(financials.get("periods"))
        valid_financial_periods = self.stock_data_service.valid_financial_periods(raw_financial_periods)
        full_financial_periods = self.stock_data_service.full_financial_periods(valid_financial_periods)
        ratio_financial_periods = self.stock_data_service.ratio_financial_periods(valid_financial_periods)
        financial_periods = full_financial_periods or valid_financial_periods
        financial_balance = self._dict(normalized.get("financial_balance"))
        data_quality = self._dict(normalized.get("data_quality"))
        source_success = self._dict(normalized.get("_source_success"))
        company = normalized.get("company") or self.stock_data_service.extract_company(stock_detail)
        data_quality_notes = self._build_data_quality_notes(data_quality, full_financial_periods, warnings)
        raw_hose_market_context = self._dict(normalized.get("hose_market_context"))
        raw_market_general_context = self._dict(normalized.get("market_general_context"))
        market_context_debug = self._normalize_market_context(raw_hose_market_context, raw_market_general_context)
        effective_market_context = self._dict(market_context_debug.get("normalized")) or self._effective_market_context(
            raw_hose_market_context,
            raw_market_general_context,
        )
        hose_market_context = effective_market_context
        market_general_context = dict(raw_market_general_context)
        if market_context_debug.get("normalized"):
            market_general_context.setdefault("normalized", market_context_debug["normalized"])
        industry_peer_context = self._dict(normalized.get("industry_peer_context"))
        peers = self._prepare_peers(self._list(industry_peer_context.get("peers")), symbol=symbol)
        if peers:
            industry_peer_context = dict(industry_peer_context)
            industry_peer_context["peers"] = peers
        company_overview = self._dict(normalized.get("company_overview"))
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
            "hose_market_context": effective_market_context,
            "industry_peer_context": industry_peer_context,
            "data_quality": data_quality,
            "external_research_context": research_context.model_dump() if research_context else {"items": []},
        }
        if self.settings.enable_scoring:
            scores = self.scoring_service.build_scores(scoring_input)
        else:
            scores = self._disabled_scores()
            data_quality_notes.append("Scoring đang tắt bởi ENABLE_SCORING=false.")

        technical_notes = self._dedupe([*data_quality_notes, *(warnings or [])])
        user_data_notes = self._friendly_notes(technical_notes)
        summary = {
            "symbol": symbol,
            "company": company,
            "scope_exchange": scope_exchange or normalized.get("exchange") or "HOSE",
            "disclaimer": DEFAULT_DISCLAIMER,
            "data_coverage": {
                "backend_stock_detail_loaded": backend_stock_detail_loaded,
                "analysis_data_loaded": analysis_data_loaded,
                "latest_price_loaded": self._has_latest_price(latest_market),
                "financials_loaded": bool(full_financial_periods),
                "financial_periods_count": len(full_financial_periods),
                "financial_ratios_loaded": bool(ratio_financial_periods) or bool(data_quality.get("financial_ratios_loaded")),
                "financial_ratio_periods_count": len(ratio_financial_periods) or int(data_quality.get("financial_ratio_periods_count") or 0),
                "price_history_points": len(price_history),
                "market_context_loaded": self._has_market_context(effective_market_context),
                "peer_context_loaded": bool(peers),
                "external_research_items": len(research_context.items) if research_context else 0,
                "watchlist_loaded": self._source_loaded(source_success, "watchlist_loaded", fallback=False),
            },
            "latest_market": latest_market,
            "price_history": price_history,
            "momentum": self._build_momentum(price_history),
            "bctc_3q": {
                "has_bctc": bool(full_financial_periods),
                "has_financial_ratios": bool(ratio_financial_periods),
                "periods": financial_periods[:3],
                "total_periods_available": len(full_financial_periods),
                "total_ratio_periods_available": len(ratio_financial_periods),
                "source": financials.get("source") or data_quality.get("financial_source") or data_quality.get("source"),
                "data_quality_notes": user_data_notes,
                "technical_data_quality_notes": technical_notes,
            },
            "financial_balance": financial_balance,
            "company_overview": company_overview,
            "hose_market_context": hose_market_context,
            "industry_peer_context": industry_peer_context,
            "market_general_context": market_general_context,
            "market_context_debug": market_context_debug,
            "same_industry_recommendation": self._dict(normalized.get("same_industry_recommendation")),
            "data_quality": data_quality,
            "data_quality_notes": user_data_notes,
            "technical_data_quality_notes": technical_notes,
            "scores": scores,
            "score_explanations": self._string_list(scores.get("score_explanations")),
            "strengths": self._default_strengths(latest_market, financial_periods, scores, company_overview),
            "weaknesses": self._default_weaknesses(data_quality, scores),
            "external_research_context": research_context.model_dump() if research_context else {"enabled": False, "status": "disabled", "items": []},
            "system_decision": self._build_system_decision(scores, data_quality, bool(full_financial_periods), hose_market_context),
            "investment_plan": {"decision": {}, "reference_levels": {}, "position_sizing": {}, "action_table": []},
            "warnings": self._dedupe([*(warnings or []), *self._string_list(data_quality.get("warnings"))]),
        }
        summary["report_presentation"] = self._build_report_presentation(
            summary=summary,
            technical_notes=technical_notes,
            user_data_notes=user_data_notes,
            research_context=research_context,
        )
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
        primary = self._dict(market_context.get("primary_index"))
        if primary:
            return self._has_market_context(primary)
        return any(
            market_context.get(key) not in (None, "", {}, [])
            for key in (
                "vnindex",
                "vn_index",
                "index_value",
                "indexValue",
                "change",
                "change_percent",
                "changePercent",
                "liquidity",
                "volume",
                "matchedVolume",
                "total_volume",
                "totalValue",
                "total_value",
                "trading_value_billion",
                "tradingValueBillion",
                "regime",
                "status",
                "market_health_score",
                "marketScore",
                "healthScore",
                "foreign_net",
            )
        )

    def _effective_market_context(self, hose_market_context: dict[str, Any], market_general_context: dict[str, Any]) -> dict[str, Any]:
        if self._has_market_context(hose_market_context):
            return hose_market_context
        primary = self._dict(market_general_context.get("primary_index"))
        if self._has_market_context(primary):
            return primary
        if self._has_market_context(market_general_context):
            return market_general_context
        return {}

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

    def _friendly_notes(self, notes: list[str]) -> list[str]:
        mapped = [self._friendly_note(note) for note in notes]
        return self._dedupe(mapped)

    def _friendly_note(self, note: str) -> str:
        lower = note.lower()
        if (
            "không tìm thấy bảng tài chính trong html tĩnh" in lower
            and "chuyển sang" in lower
        ):
            return "Hệ thống đã chuyển sang đối chiếu dữ liệu tài chính từ nguồn công khai khi dữ liệu nội bộ chưa đủ."
        if (
            "không tìm thấy bảng tài chính" in lower
            or "playwright" in lower
            or "browser rendering" in lower
            or "render bằng trình duyệt" in lower
            or "selector" in lower
            or "dom" in lower
            or "html vietstock" in lower
            or "notimplementederror" in lower
            or "subprocess" in lower
            or "timeouterror" in lower
            or "timeout" in lower
            or "browser goto" in lower
            or "trình duyệt" in lower
        ):
            return "Dữ liệu tài chính từ nguồn công khai chưa được trích xuất thành công trong lần chạy này; báo cáo không suy diễn thêm khi chưa có số liệu xác thực."
        if "field thiếu từ backend" in lower or "missingfields" in lower or "missing fields" in lower:
            return "Một số nhóm dữ liệu định lượng chưa đủ độ phủ; phần chính của báo cáo sẽ chỉ dùng các dữ liệu đã xác thực được."
        if "financials" in lower or "bctc" in lower or "factfinancialstatements" in lower:
            return "Bộ dữ liệu báo cáo tài chính hiện chưa đủ để đưa ra kết luận sâu về tăng trưởng và chất lượng lợi nhuận."
        if "industry_id" in lower or "peer" in lower or "industrypeercontext" in lower:
            return "Dữ liệu ngành/peer hiện chưa đủ để lập bảng so sánh định lượng đáng tin cậy."
        if "watchlists" in lower or "watchlist" in lower or "401" in lower or "unauthorized" in lower:
            return "Danh sách theo dõi cá nhân chưa được sử dụng trong báo cáo này; phân tích vẫn dựa trên dữ liệu cổ phiếu và nguồn nghiên cứu hiện có."
        if "đơn vị" in lower or "unit" in lower or "market_cap" in lower:
            return "Một số chỉ tiêu tài chính cần được đối chiếu đơn vị trước khi dùng để so sánh tuyệt đối."
        if "vietstock finance" in lower and "bổ sung dữ liệu tài chính" in lower:
            return "Báo cáo đã bổ sung dữ liệu tài chính từ Vietstock Finance để đối chiếu với dữ liệu nội bộ."
        if "/api/stocks" in lower or "analysis-data" in lower or "backend" in lower:
            return "Nguồn dữ liệu nội bộ chưa phản hồi đầy đủ tại thời điểm tạo báo cáo; các kết luận cần được đọc với mức thận trọng cao."
        if "external research" in lower or "research" in lower or "adapter" in lower:
            return "Nguồn tin tức/nghiên cứu bên ngoài chưa đủ độ phủ; cần kiểm chứng thêm từ nguồn công bố gốc."
        if "chart" in lower or "price history" in lower or "lịch sử giá" in lower:
            return "Chuỗi giá hiện chưa đủ dài để đánh giá xu hướng và biến động một cách chắc chắn."
        return note

    def _build_report_presentation(
        self,
        *,
        summary: dict[str, Any],
        technical_notes: list[str],
        user_data_notes: list[str],
        research_context: ExternalResearchContext | None,
    ) -> dict[str, Any]:
        latest = self._dict(summary.get("latest_market"))
        momentum = self._dict(summary.get("momentum"))
        scores = self._dict(summary.get("scores"))
        coverage = self._dict(summary.get("data_coverage"))
        financial_periods = self._list(self._dict(summary.get("bctc_3q")).get("periods"))
        peer_context = self._dict(summary.get("industry_peer_context"))
        peers = self._list(peer_context.get("peers"))
        research_items = research_context.items if research_context else []
        decision = self._dict(summary.get("system_decision"))
        market_view = self._market_context_view(summary)
        research_insights = self._research_insights(research_items, symbol=summary.get("symbol"))
        research_positive_notes = self._research_thesis_notes(research_insights, "positive_catalysts")
        research_risk_notes = self._research_thesis_notes(research_insights, "risks")
        confidence_score = normalize_percent_score(scores.get("score_confidence"))

        return {
            "executive_summary": {
                "status": decision.get("status") or "CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN",
                "main_thesis": self._build_main_thesis(summary),
                "key_positives": self._dedupe([*self._presentation_strengths(summary), *research_positive_notes[:2]]),
                "key_risks": self._dedupe([*self._presentation_risks(summary, user_data_notes), *research_risk_notes[:2]]),
                "confidence": confidence_score,
                "confidence_score": confidence_score,
                "confidence_ratio": scores.get("score_confidence") if isinstance(scores.get("score_confidence"), (int, float)) and 0 <= scores.get("score_confidence") <= 1 else None,
                "display_confidence": display_percent_value(scores.get("score_confidence")),
                "confidence_label": self._confidence_label(scores.get("score_confidence")),
                "checks_before_action": self._checks_before_action(summary),
            },
            "business_overview": self._business_overview(summary, research_items),
            "market_context": market_view.get("narrative"),
            "market_context_view": market_view,
            "price_momentum": self._price_momentum_commentary(latest, momentum),
            "financial_analysis": self._financial_commentary(financial_periods, summary),
            "valuation": self._valuation_commentary(summary),
            "peer_note": self._peer_note(peers),
            "reference_candidates": self._reference_candidates(summary),
            "research_insights": research_insights,
            "score_cards": self._score_cards(scores, summary),
            "roadmap": self._roadmap(summary),
            "coverage_rows": self._coverage_rows(summary),
            "data_quality": {
                "user_notes": user_data_notes,
                "technical_notes": technical_notes,
            },
            "missing_display": "Chưa đủ dữ liệu xác thực",
            "summary_bar": {
                "latest_price": latest.get("close_price") or latest.get("close"),
                "chart_return": momentum.get("change_pct"),
                "overall_score": scores.get("overall_score"),
                "risk_label": scores.get("risk_label"),
                "financial_periods_count": coverage.get("financial_periods_count"),
                "data_confidence": confidence_score,
                "data_confidence_display": display_percent_value(scores.get("score_confidence")),
            },
        }

    def _build_main_thesis(self, summary: dict[str, Any]) -> str:
        scores = self._dict(summary.get("scores"))
        decision = self._dict(summary.get("system_decision"))
        overall = scores.get("overall_score")
        label = scores.get("overall_label")
        if isinstance(overall, (int, float)):
            return (
                f"Hệ thống đang đánh giá mã ở mức {label} với điểm tổng {overall}/100. "
                "Đây là tín hiệu định lượng tham khảo, cần đối chiếu thêm với BCTC, bối cảnh ngành và nguồn công bố gốc."
            )
        return self._text(decision.get("action"), "Chưa đủ dữ liệu xác thực để hình thành luận điểm đầu tư đáng tin cậy.")

    def _presentation_strengths(self, summary: dict[str, Any]) -> list[str]:
        strengths = self._string_list(summary.get("strengths"))
        return strengths or ["Chưa có đủ bằng chứng định lượng để xác định điểm mạnh nổi bật."]

    def _presentation_risks(self, summary: dict[str, Any], user_data_notes: list[str]) -> list[str]:
        risks = self._string_list(summary.get("weaknesses"))
        risks.extend(self._risk_notes_only(user_data_notes)[:3])
        return self._dedupe(risks) or ["Cần theo dõi thêm vì dữ liệu đầu vào còn hạn chế."]

    def _checks_before_action(self, summary: dict[str, Any]) -> list[str]:
        checks = [
            "Đối chiếu số liệu giá, thanh khoản và định giá với nguồn dữ liệu gốc.",
            "Kiểm tra BCTC gần nhất, đặc biệt là lợi nhuận sau thuế, dòng tiền và nợ vay.",
            "Xem lại tin tức/nghiên cứu gần đây từ URL nguồn trước khi ra quyết định.",
            "Đánh giá lại bối cảnh VNINDEX/nhóm ngành nếu thị trường chuyển sang trạng thái rủi ro cao.",
        ]
        if not self._list(self._dict(summary.get("industry_peer_context")).get("peers")):
            checks.append("Bổ sung peer đáng tin cậy trước khi so sánh định giá tương quan.")
        return checks

    def _business_overview(self, summary: dict[str, Any], research_items: list[Any]) -> dict[str, Any]:
        company = self._text(summary.get("company"), "Doanh nghiệp")
        company_overview = self._dict(summary.get("company_overview"))
        industry = self._dict(self._dict(summary.get("industry_peer_context")).get("industry"))
        merged_industry = dict(industry)
        sector = (
            merged_industry.get("industry_level_1")
            or merged_industry.get("sector")
            or merged_industry.get("sector_name")
            or company_overview.get("industry_level_1")
            or company_overview.get("sector")
        )
        group = (
            merged_industry.get("industry_level_2")
            or merged_industry.get("industry_group")
            or merged_industry.get("group")
            or merged_industry.get("sub_sector")
            or company_overview.get("industry_level_2")
        )
        detail = (
            merged_industry.get("industry_level_3")
            or merged_industry.get("industry")
            or merged_industry.get("industry_name")
            or company_overview.get("industry_level_3")
            or company_overview.get("industry")
        )
        if sector:
            merged_industry.setdefault("sector", sector)
            merged_industry.setdefault("industry_level_1", sector)
        if group:
            merged_industry.setdefault("industry_group", group)
            merged_industry.setdefault("industry_level_2", group)
        if detail:
            merged_industry.setdefault("industry", detail)
            merged_industry.setdefault("industry_level_3", detail)
        if company_overview.get("source") and not merged_industry.get("source"):
            merged_industry["source"] = company_overview.get("source")
        if company_overview.get("source_url") and not merged_industry.get("source_url"):
            merged_industry["source_url"] = company_overview.get("source_url")
        source_titles = [item.title for item in research_items[:3] if getattr(item, "title", None)]
        business_text = self._text(company_overview.get("business_overview"), "")
        source_names = []
        company_source = company_overview.get("source_display") or self._company_source_display(company_overview.get("source"))
        industry_source = merged_industry.get("source_display") or self._source_display(merged_industry.get("source"))
        if industry_source == "CafeF" and company_source.startswith("CafeF"):
            industry_source = company_source
        for source in (company_source, industry_source):
            if source and source != "Chưa xác minh" and source not in source_names:
                source_names.append(source)
        source_note = (
            "Nguồn đối chiếu: " + " / ".join(source_names) + "."
            if source_names
            else "Các nhận định ngành chỉ dùng khi có dữ liệu nội bộ hoặc nguồn công khai đi kèm."
        )
        leadership = self._list(company_overview.get("leadership"))
        ownership = self._list(company_overview.get("ownership"))
        if business_text:
            source = source_names[0] if source_names else "nguồn công khai"
            description = (
                f"{company} được mô tả từ nguồn {source}: {business_text} "
                "Báo cáo ưu tiên trình bày hồ sơ doanh nghiệp, ban lãnh đạo, dữ liệu sở hữu và bối cảnh ngành đã xác minh."
            )
        elif merged_industry:
            labels = []
            if group and group != sector:
                labels.append(f"nhóm ngành {group}")
            if detail and detail not in {sector, group}:
                labels.append(f"ngành chi tiết {detail}")
            industry_text = ", ".join(labels) if labels else "nhóm ngành liên quan"
            source_phrase = " và ".join(source_names) if source_names else "nguồn dữ liệu hiện có"
            description = (
                f"{company} được đối chiếu từ {source_phrase}. Doanh nghiệp thuộc {industry_text}. "
                "Báo cáo ưu tiên trình bày hồ sơ doanh nghiệp, ban lãnh đạo và dữ liệu sở hữu nếu nguồn công khai có thể trích xuất được. "
                "Nhóm ngành được dùng làm cơ sở tham chiếu khi so sánh peer, không thay thế cho phân tích định lượng."
            )
            if group and not detail:
                description += " Dữ liệu ngành chi tiết hiện chưa đủ để trình bày sâu hơn."
        else:
            description = (
                f"{company} được phân tích dựa trên dữ liệu giá, BCTC và nguồn nghiên cứu hiện có. "
                "Thông tin hồ sơ doanh nghiệp, ban lãnh đạo, sở hữu và ngành từ nguồn công khai chưa đủ để trình bày sâu hơn trong lần chạy này."
            )
        drivers = self._industry_driver_hints(merged_industry, source_titles)
        if leadership:
            drivers.append("Thông tin ban lãnh đạo từ CafeF có thể dùng để kiểm tra cấu trúc quản trị trước khi đánh giá sâu.")
        if ownership:
            drivers.append("Thông tin sở hữu từ CafeF giúp bổ sung góc nhìn về cổ đông lớn và mức độ tập trung sở hữu.")
        return {
            "company_name": company_overview.get("company_name") or company,
            "exchange": company_overview.get("exchange") or summary.get("scope_exchange") or summary.get("exchange"),
            "description": description,
            "industry": merged_industry or {},
            "drivers": self._dedupe(drivers),
            "leadership": leadership[:5],
            "ownership": ownership[:5],
            "source_note": source_note,
        }

    def _industry_driver_hints(self, industry: dict[str, Any], source_titles: list[str]) -> list[str]:
        industry_text = " ".join(str(value) for value in industry.values()).lower()
        hints: list[str] = []
        if "thép" in industry_text or "steel" in industry_text:
            hints.extend(["Chu kỳ giá thép/HRC và quặng sắt.", "Nhu cầu xây dựng, bất động sản, đầu tư công và xuất khẩu."])
        elif "công nghệ" in industry_text or "technology" in industry_text:
            hints.extend(["Nhu cầu chuyển đổi số, xuất khẩu phần mềm và biên lợi nhuận dịch vụ CNTT.", "Tăng trưởng đơn hàng và tỷ giá đối với doanh thu nước ngoài."])
        elif "ngân hàng" in industry_text or "tổ chức tín dụng" in industry_text or "tai chinh" in industry_text:
            hints.extend([
                "Tăng trưởng tín dụng, biên lãi ròng và chi phí vốn.",
                "Chất lượng tài sản, nợ xấu, trích lập dự phòng và khả năng duy trì tiền gửi CASA.",
            ])
        if source_titles:
            hints.append("Tin tức gần đây cần được đọc cùng ngày đăng và nguồn gốc để đánh giá catalyst.")
        return hints or ["Chưa đủ dữ liệu xác thực để mô tả chu kỳ ngành cụ thể."]

    def _company_source_display(self, value: Any) -> str:
        source = self._source_display(value)
        if source == "CafeF":
            return "CafeF thông tin doanh nghiệp"
        return source

    def _normalize_market_context(self, hose_market_context: dict[str, Any], market_general_context: dict[str, Any]) -> dict[str, Any]:
        candidates = self._market_context_candidates(hose_market_context, market_general_context)
        raw_keys_found = sorted({key for item in candidates for key in item.keys()})
        if not candidates:
            return {"raw_keys_found": [], "normalized": {}, "missing_fields": []}

        index_name = self._text(
            self._market_alias_value(candidates, "index_name", "indexName", "display_symbol", "displaySymbol", "index_symbol", "indexSymbol", "symbol"),
            "VN-Index",
        )
        index_value = self._number_value(
            self._market_alias_value(candidates, "index_value", "indexValue", "vnindex", "vn_index", "close_index", "closeIndex", "index", "value")
        )
        change_percent = self._number_value(
            self._market_alias_value(candidates, "change_percent", "changePercent", "change_pct", "changePct", "percentChange", "pct_change", "change")
        )
        liquidity = self._number_value(
            self._market_alias_value(
                candidates,
                "liquidity",
                "matchedVolume",
                "matched_volume",
                "volume",
                "total_volume",
                "totalVolume",
                "tradingVolume",
                "trading_volume",
            )
        )
        trading_raw, trading_key = self._market_alias_value_with_key(
            candidates,
            "trading_value_billion",
            "tradingValueBillion",
            "total_value_billion",
            "totalValueBillion",
            "trading_value",
            "tradingValue",
            "total_value",
            "totalValue",
            "matchedValue",
            "matched_value",
        )
        trading_value_billion = self._normalize_trading_value_billion(trading_raw, trading_key)
        status = self._market_alias_value(
            candidates,
            "market_health_label",
            "marketHealthLabel",
            "status",
            "market_status",
            "marketStatus",
            "regime",
            "label",
        )
        score_direction = self._market_alias_value(candidates, "score_direction", "regime_score_direction", "scoreDirection")
        risk_flag = self._market_alias_value(candidates, "regime_score_is_risk", "regimeScoreIsRisk")
        if score_direction is None and risk_flag is True:
            score_direction = "higher_is_risk"
        raw_score = self._market_alias_value(
            candidates,
            "market_health_score",
            "marketHealthScore",
            "health_score",
            "healthScore",
            "marketScore",
            "score",
            "regime_score",
            "regimeScore",
        )
        market_health_score = self._normalize_market_health_score(raw_score, str(score_direction or "higher_is_better"))
        market_health_label = self._market_health_label(market_health_score, fallback=status)
        updated_at = self._market_alias_value(candidates, "updated_at", "updatedAt", "time", "date", "tradingDate")
        source = self._market_alias_value(candidates, "source", "source_name", "sourceName")

        normalized = {
            "index_name": index_name,
            "display_symbol": index_name,
            "index_symbol": index_name,
            "index_value": index_value,
            "vnindex": index_value,
            "change_percent": change_percent,
            "liquidity": liquidity,
            "total_volume": liquidity,
            "trading_value_billion": trading_value_billion,
            "total_value": trading_value_billion,
            "status": market_health_label,
            "regime": status,
            "market_health_score": market_health_score,
            "market_health_label": market_health_label,
            "score_direction": score_direction or "higher_is_better",
            "updated_at": updated_at,
            "source": self._source_display(source),
        }
        normalized = {key: value for key, value in normalized.items() if value not in (None, "", {}, [])}
        missing_fields = [
            field
            for field, value in (
                ("index_value", index_value),
                ("change_percent", change_percent),
                ("liquidity", liquidity),
                ("trading_value_billion", trading_value_billion),
                ("market_health_score", market_health_score),
            )
            if value is None
        ]
        return {
            "raw_keys_found": raw_keys_found,
            "normalized": normalized,
            "missing_fields": missing_fields,
        }

    def _market_context_candidates(self, hose_market_context: dict[str, Any], market_general_context: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for value in (
            hose_market_context,
            self._dict(hose_market_context.get("primary_index")),
            self._dict(hose_market_context.get("primaryIndex")),
            self._dict(market_general_context.get("primary_index")),
            self._dict(market_general_context.get("primaryIndex")),
            self._dict(market_general_context.get("market_overview")),
            self._dict(market_general_context.get("marketOverview")),
            market_general_context,
        ):
            if value and value not in candidates:
                candidates.append(value)
        return candidates

    def _market_alias_value(self, candidates: list[dict[str, Any]], *keys: str) -> Any:
        value, _ = self._market_alias_value_with_key(candidates, *keys)
        return value

    def _market_alias_value_with_key(self, candidates: list[dict[str, Any]], *keys: str) -> tuple[Any, str | None]:
        aliases = {key.lower(): key for key in keys}
        for item in candidates:
            for key in keys:
                if key in item and item[key] not in (None, "", {}, []):
                    return item[key], key
            lower_keys = {str(key).lower(): key for key in item.keys()}
            for lower, original_alias in aliases.items():
                original_key = lower_keys.get(lower)
                if original_key is not None and item[original_key] not in (None, "", {}, []):
                    return item[original_key], original_alias
        return None, None

    def _number_value(self, value: Any) -> float | None:
        if value in (None, "") or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    def _normalize_trading_value_billion(self, value: Any, source_key: str | None) -> float | None:
        numeric = self._number_value(value)
        if numeric is None:
            return None
        key = str(source_key or "").lower()
        if "billion" in key:
            return numeric
        if abs(numeric) >= 1_000_000_000:
            return numeric / 1_000_000_000
        if abs(numeric) >= 1_000_000:
            return numeric / 1_000
        return numeric

    def _market_health_label(self, score: int | None, *, fallback: Any = None) -> str:
        if score is not None:
            if score < 40:
                return "Thận trọng"
            if score < 60:
                return "Trung tính"
            if score < 75:
                return "Khá tích cực"
            return "Rất tích cực"
        return self._market_regime_label(fallback)

    def _market_context_view(self, summary: dict[str, Any]) -> dict[str, Any]:
        market = self._dict(self._dict(summary.get("market_context_debug")).get("normalized"))
        if not market:
            market_general = self._dict(summary.get("market_general_context"))
            hose = self._dict(summary.get("hose_market_context"))
            market = self._dict(self._normalize_market_context(hose, market_general).get("normalized"))
        if not market:
            return {
                "title": "Bối cảnh VNINDEX/HoSE",
                "summary": "Bối cảnh thị trường chung chưa đủ dữ liệu xác thực; cần đọc kết luận với mức thận trọng cao hơn.",
                "narrative": "Bối cảnh thị trường chung chưa đủ dữ liệu xác thực; cần đọc kết luận với mức thận trọng cao hơn.",
                "cards": [],
                "regime_score": None,
                "market_health_score": None,
                "health": {
                    "score": None,
                    "label": "Cần thêm dữ liệu",
                    "description": "0 là thận trọng hơn, 100 là tích cực hơn.",
                },
                "display_date": "Chưa xác minh",
            }

        index_value = self._first_value(market, "index_value", "vnindex", "close_index", "index", "value")
        change_pct = self._first_value(market, "change_percent", "changePercent")
        volume = self._first_value(market, "liquidity", "total_volume", "totalVolume")
        value = self._first_value(market, "trading_value_billion", "total_value", "totalValue")
        regime = self._text(market.get("status") or market.get("market_health_label") or market.get("regime"), "Trung tính")
        regime_score = self._first_value(market, "market_health_score", "regime_score", "regimeScore")
        score_direction = self._first_value(market, "score_direction", "regime_score_direction", "scoreDirection")
        if score_direction is None and market.get("regime_score_is_risk") is True:
            score_direction = "higher_is_risk"
        market_health_score = self._normalize_market_health_score(regime_score, str(score_direction or "higher_is_better"))
        market_health_label = self._market_health_label(market_health_score, fallback=regime)
        display_symbol = self._text(market.get("display_symbol") or market.get("index_symbol") or market.get("index_name"), "VN-Index")
        display_date = format_datetime_vi(market.get("updated_at") or market.get("time") or market.get("date"), include_time=True)

        narrative_parts = []
        if isinstance(index_value, (int, float)):
            narrative_parts.append(f"{display_symbol} ghi nhận {index_value:,.2f} điểm")
        else:
            narrative_parts.append(f"{display_symbol} đã có dữ liệu bối cảnh thị trường")
        if isinstance(change_pct, (int, float)):
            movement = "tăng" if change_pct > 0 else "giảm" if change_pct < 0 else "đi ngang"
            narrative_parts.append(f"{movement} {abs(change_pct):.2f}% trong phiên dữ liệu gần nhất")
        if isinstance(volume, (int, float)):
            narrative_parts.append(f"thanh khoản khoảng {self._compact_number(volume)} cổ phiếu")
        if isinstance(value, (int, float)):
            narrative_parts.append(f"giá trị giao dịch khoảng {self._format_trading_value_billion(value)}")
        narrative = ". ".join(narrative_parts) + "."
        if regime:
            narrative += f" Trạng thái thị trường được xếp loại {market_health_label}, cho thấy bối cảnh chung cần được đọc cùng tín hiệu giá và thanh khoản của từng cổ phiếu."

        cards = [
            {"label": "Chỉ số", "value": f"{display_symbol} {self._format_index_value(index_value)}" if isinstance(index_value, (int, float)) else "Chưa xác minh"},
            {"label": "Biến động", "value": self._format_percent(change_pct)},
            {"label": "Thanh khoản", "value": self._format_liquidity(volume)},
            {"label": "Giá trị giao dịch", "value": self._format_trading_value_billion(value)},
            {"label": "Trạng thái", "value": market_health_label},
            {"label": "Điểm sức khỏe thị trường", "value": f"{market_health_score}/100" if market_health_score is not None else "Chưa xác minh"},
        ]
        return {
            "title": "Bối cảnh VNINDEX/HoSE",
            "summary": narrative,
            "narrative": narrative,
            "cards": cards,
            "regime_score": regime_score,
            "market_health_score": market_health_score,
            "market_health_label": market_health_label,
            "score_direction": score_direction or "higher_is_better",
            "regime": regime,
            "index_name": display_symbol,
            "index_value": index_value,
            "display_date": display_date,
            "source": self._source_display(market.get("source")),
            "change_percent": change_pct,
            "liquidity": volume,
            "trading_value_billion": value,
            "health": {
                "score": market_health_score,
                "label": market_health_label,
                "description": "0 là thận trọng hơn, 100 là tích cực hơn.",
            },
        }

    def _market_context_commentary(self, summary: dict[str, Any]) -> str:
        return self._text(self._market_context_view(summary).get("narrative"), "Bối cảnh thị trường cần được đối chiếu thêm.")

    def _price_momentum_commentary(self, latest: dict[str, Any], momentum: dict[str, Any]) -> str:
        if not latest and not momentum:
            return "Chuỗi giá hiện chưa đủ để đánh giá xu hướng, thanh khoản và biến động."
        close = latest.get("close_price") or latest.get("close")
        change = momentum.get("change_pct")
        points = momentum.get("period_points")
        parts = []
        if isinstance(close, (int, float)):
            parts.append(f"Giá đóng cửa gần nhất trong dữ liệu giao dịch hiện có là {close:,}.")
        if isinstance(change, (int, float)):
            label = "tích cực" if change > 0 else "tiêu cực" if change < 0 else "đi ngang"
            parts.append(f"Biến động trong chuỗi chart là {change}%, tạm xếp nhãn {label}.")
        if isinstance(points, int):
            parts.append(f"Chuỗi giá có {points} điểm dữ liệu.")
        return " ".join(parts)

    def _financial_commentary(self, periods: list[dict[str, Any]], summary: dict[str, Any]) -> str:
        if not periods:
            return "Bộ dữ liệu BCTC hiện chưa đủ để phân tích xu hướng doanh thu, lợi nhuận và chất lượng bảng cân đối một cách đáng tin cậy."
        latest = periods[0]
        previous = periods[1] if len(periods) > 1 else {}
        parts = [f"Báo cáo đang dùng {len(periods)} kỳ tài chính gần nhất có trong dữ liệu đã xác thực."]
        is_bank = self.stock_data_service.looks_like_bank_period(latest)
        metrics = (
            (
                ("lợi nhuận trước thuế", "profit_before_tax"),
                ("lợi nhuận sau thuế", "profit_after_tax"),
                ("lợi nhuận cổ đông mẹ", "parent_profit"),
                ("thu nhập lãi thuần", "net_interest_income"),
                ("cho vay khách hàng", "customer_loans"),
                ("tiền gửi khách hàng", "customer_deposits"),
                ("tổng tài sản", "total_assets"),
                ("vốn chủ sở hữu", "equity"),
                ("ROE", "roe"),
                ("ROA", "roa"),
            )
            if is_bank
            else (
                ("doanh thu", "revenue"),
                ("lợi nhuận gộp", "gross_profit"),
                ("lợi nhuận trước thuế", "profit_before_tax"),
                ("lợi nhuận sau thuế", "profit_after_tax"),
                ("tổng tài sản", "total_assets"),
                ("vốn chủ sở hữu", "equity"),
                ("ROE", "roe"),
                ("ROA", "roa"),
            )
        )
        used = 0
        for label, key in metrics:
            value = self._valid_financial_value(latest, key)
            if isinstance(value, (int, float)):
                parts.append(f"Kỳ mới nhất ghi nhận {label} khoảng {value:,}.")
                used += 1
            prev = previous.get(key)
            if isinstance(value, (int, float)) and isinstance(prev, (int, float)) and prev:
                change = round((value - prev) / abs(prev) * 100, 1)
                parts.append(f"{label.capitalize()} thay đổi khoảng {change}% so với kỳ liền trước.")
        if not used:
            parts.append("Một số chỉ tiêu tài chính đã được nhận diện nhưng chưa đủ độ tin cậy để trình bày như số liệu khẳng định.")
        return " ".join(parts)

    def _valid_financial_value(self, period: dict[str, Any], key: str) -> Any:
        if not isinstance(period, dict):
            return None
        if key in {"total_assets", "equity", "customer_loans", "customer_deposits", "roa", "roe"}:
            sanitized = self.stock_data_service.sanitize_financial_period(period)
            return sanitized.get(key)
        return period.get(key)

    def _valuation_commentary(self, summary: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        scores = self._dict(summary.get("scores"))
        pe = latest.get("pe")
        pb = latest.get("pb")
        roe = latest.get("roe")
        parts = []
        if isinstance(pe, (int, float)):
            parts.append(f"P/E hiện có trong dữ liệu là {pe}.")
        if isinstance(pb, (int, float)):
            parts.append(f"P/B hiện có trong dữ liệu là {pb}.")
        if isinstance(roe, (int, float)):
            parts.append(f"ROE hiện có trong dữ liệu là {roe}%.")
        if scores.get("valuation_score") is not None:
            parts.append(f"Điểm định giá đạt {scores.get('valuation_score')}/100.")
        if not parts:
            return "Chưa đủ dữ liệu định giá xác thực để đưa ra nhận định tương quan."
        parts.append("Nếu chỉ số định giá có vẻ bất thường, cần xem đây là điểm cần kiểm chứng dữ liệu chứ không phải cơ hội chắc chắn.")
        return " ".join(parts)

    def _prepare_peers(self, peers: list[dict[str, Any]], *, symbol: str) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for peer in peers:
            item = dict(peer)
            item.setdefault("source", "Dữ liệu so sánh nội bộ")
            item.setdefault("same_industry_reason", "Được ghi nhận trong nhóm peer cùng ngành từ nguồn dữ liệu hiện có.")
            prepared.append(item)
        return self.stock_data_service.valid_peers(prepared, symbol=symbol)

    def _peer_note(self, peers: list[dict[str, Any]]) -> str:
        if peers:
            return "Bảng peer bên dưới dùng dữ liệu so sánh hiện có; cần đối chiếu ngành nghề và quy mô trước khi so sánh định giá."
        return "Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận."

    def _reference_candidates(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        recommendation = self._dict(summary.get("same_industry_recommendation"))
        candidates = self._list(recommendation.get("candidates"))
        if not candidates:
            return []
        result: list[dict[str, Any]] = []
        for item in candidates[:5]:
            confidence = item.get("confidence")
            if confidence is None:
                confidence = 0.7 if item.get("roe") or item.get("pe") else 0.45
            confidence_score = normalize_percent_score(confidence)
            result.append(
                {
                    "ticker": item.get("ticker") or item.get("symbol"),
                    "company": item.get("company") or item.get("company_name"),
                    "label": item.get("label") or ("Đáng theo dõi" if item.get("roe") or item.get("momentum_1m") else "Cần chờ xác nhận"),
                    "reason_to_watch": item.get("reason_to_watch") or "Có dữ liệu peer cùng ngành và một số chỉ tiêu tương quan có thể so sánh.",
                    "supporting_data": {
                        "close_price": item.get("close_price") or item.get("price") or self._dict(item.get("supporting_data")).get("close_price"),
                        "change_1d_percent": item.get("change_1d_percent") or self._dict(item.get("supporting_data")).get("change_1d_percent"),
                        "matched_value_billion": item.get("matched_value_billion") or self._dict(item.get("supporting_data")).get("matched_value_billion"),
                        "market_cap_billion": item.get("market_cap_billion") or item.get("market_cap") or self._dict(item.get("supporting_data")).get("market_cap_billion"),
                        "eps_4q": item.get("eps_4q") or self._dict(item.get("supporting_data")).get("eps_4q"),
                        "pe_basic": item.get("pe_basic") or item.get("pe") or self._dict(item.get("supporting_data")).get("pe_basic"),
                        "rsi_14": item.get("rsi_14") or self._dict(item.get("supporting_data")).get("rsi_14"),
                        "basic_score": item.get("basic_score") or self._dict(item.get("supporting_data")).get("basic_score"),
                        "fundamental_rating": item.get("fundamental_rating") or self._dict(item.get("supporting_data")).get("fundamental_rating"),
                        "pb": item.get("pb") or self._dict(item.get("supporting_data")).get("pb"),
                        "roe": item.get("roe") or self._dict(item.get("supporting_data")).get("roe"),
                        "momentum_1m": item.get("momentum_1m") or self._dict(item.get("supporting_data")).get("momentum_1m"),
                    },
                    "strengths": item.get("strengths") or item.get("available_data") or "",
                    "key_risk": item.get("key_risk") or "Cần kiểm chứng lại ngành, quy mô và tính cập nhật của dữ liệu trước khi so sánh.",
                    "missing_data": item.get("missing_data") or self._candidate_missing_data(item),
                    "available_data": item.get("available_data") or self._candidate_available_data(item),
                    "source": item.get("source") or recommendation.get("source") or "Dữ liệu so sánh nội bộ",
                    "source_url": item.get("source_url"),
                    "confidence": confidence,
                    "confidence_score": confidence_score,
                    "meter_percent": confidence_score,
                    "display_confidence": display_percent_value(confidence),
                }
            )
        return result

    def _candidate_available_data(self, item: dict[str, Any]) -> str:
        supporting = self._dict(item.get("supporting_data"))
        labels = []
        for key, label in (
            ("close_price", "Giá"),
            ("matched_value_billion", "GT giao dịch"),
            ("market_cap_billion", "Vốn hóa"),
            ("eps_4q", "EPS 4Q"),
            ("pe_basic", "P/E"),
            ("pe", "P/E"),
            ("pb", "P/B"),
            ("roe", "ROE"),
        ):
            value = item.get(key) if key in item else supporting.get(key)
            if value not in (None, "", [], {}):
                labels.append(label)
        return ", ".join(self._dedupe(labels))

    def _candidate_missing_data(self, item: dict[str, Any]) -> str:
        available = set(label.strip() for label in self._candidate_available_data(item).split(",") if label.strip())
        required = ["Giá", "Vốn hóa", "P/E", "P/B", "ROE"]
        missing = [label for label in required if label not in available]
        return ", ".join(missing)

    def _research_insights(self, research_items: list[Any], *, symbol: Any = None) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {
            "positive_catalysts": [],
            "risks": [],
            "background": [],
            "needs_verification": [],
        }
        seen_titles: set[str] = set()
        for item in research_items:
            title = self._text(self._item_attr(item, "title"), "")
            title_key = self._clean_title_key(title)
            if not title or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            row = self._research_row(item, symbol=symbol)
            groups[row["category"]].append(row)

        for key in groups:
            groups[key] = sorted(
                groups[key],
                key=lambda row: (row.get("confidence", 0), row.get("display_date", "")),
                reverse=True,
            )[:6]

        synthesis = self._research_synthesis(groups)
        return {
            **groups,
            "synthesis": synthesis,
            "counts": {key: len(value) for key, value in groups.items()},
        }

    def _research_row(self, item: Any, *, symbol: Any = None) -> dict[str, Any]:
        positive_flags = self._string_list(self._item_attr(item, "positive_flags"))
        negative_flags = self._string_list(self._item_attr(item, "negative_flags"))
        catalyst_flags = self._string_list(self._item_attr(item, "catalyst_flags"))
        flags = self._dedupe([*positive_flags, *negative_flags, *catalyst_flags])
        title = self._text(self._item_attr(item, "title"), "Nguồn chưa có tiêu đề")
        snippet = self._text(self._item_attr(item, "snippet"), "")
        source = self._source_display(self._item_attr(item, "source") or self._item_attr(item, "type"))
        category = self._research_category(positive_flags, negative_flags, catalyst_flags, title, snippet)
        summary_level = "title_and_snippet" if snippet else "title_only"
        confidence = self._research_confidence(item, summary_level=summary_level, flags=flags)
        confidence_score = normalize_percent_score(confidence)
        return {
            "title": title,
            "source": source,
            "url": self._item_attr(item, "url"),
            "published_at": self._item_attr(item, "published_at"),
            "display_date": format_datetime_vi(self._item_attr(item, "published_at"), include_time=True),
            "tone": self._text(self._item_attr(item, "tone"), "trung tính"),
            "category": category,
            "summary_level": summary_level,
            "impact_horizon": self._research_impact_horizon(flags, title, snippet),
            "affected_factors": self._research_factors(flags, title, snippet),
            "detailed_summary": self._research_detailed_summary(title, snippet, source, summary_level),
            "why_it_matters": self._research_why_it_matters(title, flags, category),
            "possible_impact": self._research_possible_impact(category, flags),
            "what_to_verify": self._research_verify(summary_level, symbol=symbol),
            "confidence": confidence,
            "confidence_score": confidence_score,
            "meter_percent": confidence_score,
            "display_confidence": display_percent_value(confidence),
            "confidence_label": self._confidence_label(confidence),
            "flags": flags,
        }

    def _research_category(self, positive_flags: list[str], negative_flags: list[str], catalyst_flags: list[str], title: str, snippet: str) -> str:
        text = f"{title} {snippet}".lower()
        if negative_flags or any(keyword in text for keyword in ("rủi ro", "giảm lợi nhuận", "bán ròng", "lỗ", "hạ khuyến nghị")):
            return "risks"
        if positive_flags or catalyst_flags:
            return "positive_catalysts"
        if any(keyword in text for keyword in ("cần kiểm chứng", "tin đồn", "dự kiến", "có thể")):
            return "needs_verification"
        return "background"

    def _research_impact_horizon(self, flags: list[str], title: str, snippet: str) -> str:
        text = " ".join([title, snippet, *flags]).lower()
        if any(keyword in text for keyword in ("kết quả kinh doanh", "lợi nhuận", "bán ròng", "mua ròng", "giá thép", "hrc")):
            return "Ngắn đến trung hạn"
        if any(keyword in text for keyword in ("dự án", "m&a", "tăng vốn", "mở rộng", "hợp đồng")):
            return "Trung hạn"
        return "Bối cảnh"

    def _research_factors(self, flags: list[str], title: str, snippet: str) -> list[str]:
        text = " ".join([title, snippet, *flags]).lower()
        factors: list[str] = []
        if any(keyword in text for keyword in ("lợi nhuận", "kết quả kinh doanh", "doanh thu")):
            factors.append("Tăng trưởng lợi nhuận")
        if any(keyword in text for keyword in ("cổ tức", "chia thưởng")):
            factors.append("Chính sách cổ đông")
        if any(keyword in text for keyword in ("mua ròng", "bán ròng", "khối ngoại")):
            factors.append("Dòng tiền ngoại")
        if any(keyword in text for keyword in ("thép", "hrc", "quặng", "xây dựng", "bất động sản", "đầu tư công")):
            factors.append("Chu kỳ ngành")
        if any(keyword in text for keyword in ("hợp đồng", "dự án", "m&a", "tăng vốn", "mở rộng")):
            factors.append("Catalyst doanh nghiệp")
        return self._dedupe(factors) or ["Bối cảnh thông tin"]

    def _research_detailed_summary(self, title: str, snippet: str, source: str, summary_level: str) -> str:
        if summary_level == "title_and_snippet":
            return (
                f"Nguồn {source} ghi nhận tiêu đề: \"{title}\". "
                f"Trích yếu hiện có cho biết: {snippet}. "
                "Báo cáo chỉ sử dụng phần tiêu đề/trích yếu đã thu thập được như bằng chứng ngữ cảnh, chưa xem đây là kết luận đầy đủ của bài viết. "
                "Người đọc nên mở URL gốc để kiểm tra chi tiết, ngày công bố và phạm vi tác động."
            )
        return (
            f"Nguồn {source} ghi nhận tiêu đề: \"{title}\". "
            "Trong lần chạy này chỉ có tiêu đề, chưa có nội dung đầy đủ để phân tích sâu. "
            "Thông tin được giữ ở nhóm cần kiểm chứng hoặc bối cảnh, không dùng để suy diễn số liệu tài chính."
        )

    def _research_why_it_matters(self, title: str, flags: list[str], category: str) -> str:
        if flags:
            return "Thông tin liên quan đến " + ", ".join(flags[:5]) + "; mức độ tác động cần được kiểm chứng từ nguồn gốc."
        if category == "risks":
            return "Thông tin có sắc thái thận trọng, cần đọc cùng diễn biến giá và số liệu tài chính mới nhất."
        if category == "positive_catalysts":
            return "Thông tin có thể hỗ trợ luận điểm tích cực nếu được xác nhận bằng dữ liệu tài chính hoặc công bố chính thức."
        return "Thông tin giúp bổ sung bối cảnh ngành/doanh nghiệp, chưa đủ để xem là catalyst chính."

    def _research_possible_impact(self, category: str, flags: list[str]) -> str:
        if category == "risks":
            return "Có thể làm giảm mức tự tin của luận điểm nếu xuất hiện cùng thanh khoản yếu hoặc kết quả kinh doanh kém."
        if category == "positive_catalysts":
            return "Có thể cải thiện tâm lý và kỳ vọng nếu được xác nhận bằng kết quả kinh doanh, dòng tiền hoặc công bố chính thức."
        if category == "needs_verification":
            return "Chỉ nên xem là tín hiệu cần kiểm tra thêm, chưa dùng để nâng/hạ quan điểm."
        return "Giúp giải thích bối cảnh, tác động định lượng chưa rõ."

    def _research_verify(self, summary_level: str, *, symbol: Any = None) -> str:
        symbol_text = str(symbol or "").upper()
        base = "Đối chiếu URL gốc, ngày đăng, doanh nghiệp được nhắc tới và số liệu trong bài."
        if symbol_text:
            base += f" Kiểm tra bài viết có nói trực tiếp đến {symbol_text} hay chỉ nói về công ty con/nhóm ngành."
        if summary_level == "title_only":
            base += " Vì chỉ có tiêu đề, cần đọc toàn văn trước khi sử dụng trong luận điểm."
        return base

    def _research_confidence(self, item: Any, *, summary_level: str, flags: list[str]) -> float:
        relevance = self._item_attr(item, "relevance_score")
        score = 0.45
        if isinstance(relevance, (int, float)):
            score = max(score, min(float(relevance), 0.95))
        if summary_level == "title_and_snippet":
            score += 0.05
        if flags:
            score += 0.05
        return round(min(score, 0.95), 2)

    def _research_synthesis(self, groups: dict[str, list[dict[str, Any]]]) -> str:
        positive = len(groups.get("positive_catalysts") or [])
        risks = len(groups.get("risks") or [])
        background = len(groups.get("background") or [])
        verification = len(groups.get("needs_verification") or [])
        total = positive + risks + background + verification
        if not total:
            return "Chưa có đủ tin tức/nghiên cứu bên ngoài đã xác thực để bổ sung luận điểm."
        return (
            f"Tin tức được phân loại thành {positive} catalyst tích cực, {risks} tín hiệu rủi ro, "
            f"{background} thông tin nền và {verification} mục cần kiểm chứng. "
            "Các mục này chỉ là bằng chứng ngữ cảnh; báo cáo không dùng chúng để tạo số liệu tài chính mới."
        )

    def _research_thesis_notes(self, insights: dict[str, Any], key: str) -> list[str]:
        items = insights.get(key)
        if not isinstance(items, list):
            return []
        return [self._text(item.get("why_it_matters"), "") for item in items if isinstance(item, dict) and item.get("why_it_matters")]

    def _item_attr(self, item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    def _clean_title_key(self, title: str) -> str:
        return re.sub(r"\W+", " ", self._text(title, "").lower()).strip()

    def _score_cards(self, scores: dict[str, Any], summary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        definitions = [
            ("valuation_score", "Định giá", "P/E, forward P/E, P/B và ROE nếu có."),
            ("quality_score", "Chất lượng", "ROE, ROS, ROAA và lợi nhuận sau thuế nếu có."),
            ("growth_score", "Tăng trưởng", "Xu hướng doanh thu/lợi nhuận qua các kỳ BCTC."),
            ("momentum_score", "Động lượng giá", "Biến động giá trong chuỗi giá hiện có."),
            ("liquidity_score", "Thanh khoản", "Volume và giá trị giao dịch ước tính."),
            ("size_score", "Quy mô", "Giá trị vốn hóa nếu dữ liệu có sẵn."),
            ("risk_score", "Rủi ro", "Beta, volatility/drawdown, bối cảnh thị trường và dữ liệu còn thiếu."),
        ]
        explanation_map = self._dict(scores.get("score_explanation_map"))
        cards = []
        for key, label, data_used in definitions:
            score = scores.get(key)
            normalized_score = normalize_score_0_100(score)
            tag = self._score_label(score, inverse=(key == "risk_score"))
            description = self._text(explanation_map.get(key), "Điểm được tính từ các dữ liệu định lượng hiện có.")
            cards.append(
                {
                    "key": key,
                    "label": label,
                    "score": normalized_score,
                    "meter_percent": normalized_score,
                    "display_value": str(normalized_score) if normalized_score is not None else None,
                    "unit": None,
                    "scale": "0-100",
                    "tag": tag,
                    "score_label": tag,
                    "description": description,
                    "reason": description,
                    "data_used": data_used,
                    "could_improve": "Bổ sung dữ liệu nhiều kỳ và peer đáng tin cậy sẽ giúp điểm này chính xác hơn.",
                }
            )
        confidence_score = normalize_percent_score(scores.get("score_confidence"))
        confidence_tag = self._confidence_label(scores.get("score_confidence"))
        confidence_description = self._text(
            explanation_map.get("data_confidence"),
            "Tỷ lệ tin cậy dữ liệu xét độ phủ giá, BCTC, bối cảnh thị trường, peer và nguồn nghiên cứu bên ngoài.",
        )
        cards.append(
            {
                "key": "data_confidence",
                "label": "Tỷ lệ tin cậy dữ liệu",
                "score": confidence_score,
                "meter_percent": confidence_score,
                "display_value": display_percent_value(scores.get("score_confidence")),
                "unit": "%",
                "scale": "0-100",
                "tag": confidence_tag,
                "score_label": confidence_tag,
                "description": confidence_description,
                "reason": confidence_description,
                "data_used": "Độ phủ dữ liệu, ghi chú chất lượng dữ liệu và nguồn nghiên cứu bên ngoài.",
                "could_improve": "Cải thiện khi có đủ BCTC, peer, market context và nguồn tin xác thực.",
            }
        )
        return cards

    def _score_label(self, score: Any, *, inverse: bool = False) -> str:
        if not isinstance(score, (int, float)):
            return "Chưa xác minh"
        if inverse:
            if score <= 30:
                return "Rủi ro thấp"
            if score <= 60:
                return "Rủi ro trung bình"
            if score <= 80:
                return "Rủi ro cao"
            return "Rủi ro rất cao"
        if score >= 75:
            return "Tích cực"
        if score >= 60:
            return "Khá tích cực"
        if score >= 40:
            return "Trung tính"
        return "Yếu"

    def _confidence_label(self, confidence: Any) -> str:
        score = normalize_percent_score(confidence)
        if score is None:
            return "Chưa xác minh"
        if score >= 80:
            return "Cao"
        if score >= 60:
            return "Trung bình"
        if score >= 40:
            return "Thấp"
        return "Rất thấp"

    def _roadmap(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "phase": "Theo dõi ngắn hạn",
                "horizon": "1-2 tuần",
                "focus": "Quan sát giá đóng cửa, thanh khoản, dòng tiền ngoại và phản ứng với tin tức mới.",
            },
            {
                "phase": "Xác nhận xu hướng",
                "horizon": "1-3 tháng",
                "focus": "Đánh giá lại momentum, VNINDEX/nhóm ngành và các catalyst đã được xác thực.",
            },
            {
                "phase": "Đánh giá lại sau BCTC",
                "horizon": "Kỳ báo cáo tiếp theo",
                "focus": "Kiểm tra doanh thu, lợi nhuận sau thuế, biên lợi nhuận, nợ vay và dòng tiền.",
            },
            {
                "phase": "Kiểm soát rủi ro",
                "horizon": "Liên tục",
                "focus": "Thận trọng nếu thanh khoản suy yếu, thị trường chung chuyển sang trạng thái phòng thủ hoặc dữ liệu định lượng bị thiếu đáng kể.",
            },
        ]

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
            reasons.append("Bối cảnh thị trường đang nghiêng về thận trọng nên cần hạ mức tự tin của tín hiệu.")
        if isinstance(overall, (int, float)):
            reasons.append(f"Điểm tổng hiện tại là {overall}/100, nhãn {scores.get('overall_label')}.")
        if isinstance(risk, (int, float)):
            reasons.append(f"Điểm rủi ro là {risk}/100, nhãn rủi ro {scores.get('risk_label')}.")
        if missing_fields:
            blockers.append("Một số nhóm dữ liệu đầu vào chưa đủ độ phủ để hỗ trợ kết luận mạnh.")

        return {
            "status": status,
            "action": action,
            "reasons": reasons or ["Cần kiểm tra thêm vì dữ liệu định lượng còn hạn chế."],
            "blockers": blockers,
            "confidence": confidence,
            "note": DEFAULT_DISCLAIMER,
        }

    def _default_strengths(self, latest_market: dict[str, Any], periods: list[dict[str, Any]], scores: dict[str, Any], company_overview: dict[str, Any] | None = None) -> list[str]:
        strengths: list[str] = []
        if company_overview:
            strengths.append("Thông tin doanh nghiệp/ngành đã được đối chiếu từ nguồn công khai để hỗ trợ phần tổng quan.")
        if latest_market:
            strengths.append("Dữ liệu giao dịch mới nhất đã được ghi nhận và dùng làm cơ sở cho phần định lượng.")
        if periods:
            strengths.append(f"Báo cáo có {len(periods)} kỳ tài chính để phân tích xu hướng doanh thu, lợi nhuận và bảng cân đối.")
        if isinstance(scores.get("overall_score"), int):
            strengths.append("Hệ thống chấm điểm định lượng đã tổng hợp các yếu tố định giá, chất lượng, tăng trưởng, động lượng và rủi ro.")
        return strengths

    def _default_weaknesses(self, data_quality: dict[str, Any], scores: dict[str, Any]) -> list[str]:
        weaknesses = self._risk_notes_only(self._friendly_notes(self._string_list(data_quality.get("warnings"))))
        missing = self._string_list(data_quality.get("missing_fields"))
        if missing:
            weaknesses.append("Một số nhóm dữ liệu định lượng chưa đủ độ phủ để hỗ trợ kết luận mạnh.")
        if (scores.get("score_confidence") or 0) < 0.6:
            weaknesses.append("Tỷ lệ tin cậy chấm điểm còn thấp do dữ liệu đầu vào chưa đầy đủ.")
        return weaknesses or ["Cần tiếp tục kiểm chứng dữ liệu gốc trước khi sử dụng báo cáo."]

    def _risk_notes_only(self, notes: list[str]) -> list[str]:
        return [note for note in self._string_list(notes) if not self._is_source_or_process_note(note)]

    def _is_source_or_process_note(self, note: Any) -> bool:
        text = str(note or "").lower()
        source_markers = (
            "đã đối chiếu",
            "đã bổ sung",
            "nguồn công khai",
            "cafef",
            "vietstock",
            "google news",
            "file markdown",
            "file html",
            "báo cáo đã tạo",
            "danh sách theo dõi cá nhân chưa được sử dụng",
        )
        return any(marker in text for marker in source_markers)

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

    def _coverage_rows(self, summary: dict[str, Any]) -> list[dict[str, str]]:
        coverage = self._dict(summary.get("data_coverage"))
        financial_source = self._financial_source_label(summary)
        financial_periods = coverage.get("financial_periods_count") or 0
        ratio_periods = coverage.get("financial_ratio_periods_count") or 0
        rows = [
            {
                "label": "Giá và thanh khoản",
                "group": "Giá và thanh khoản",
                "status": self._coverage_code(coverage.get("latest_price_loaded")),
                "status_label": self._coverage_status(coverage.get("latest_price_loaded")),
                "description": "Đã có giá, khối lượng và chỉ tiêu giao dịch gần nhất." if coverage.get("latest_price_loaded") else "Chưa đủ giá/khối lượng mới nhất để đọc thanh khoản.",
                "note": "Đã có giá, khối lượng và chỉ tiêu giao dịch gần nhất." if coverage.get("latest_price_loaded") else "Chưa đủ giá/khối lượng mới nhất để đọc thanh khoản.",
            },
            {
                "label": "Chuỗi giá",
                "group": "Chuỗi giá",
                "status": "available" if (coverage.get("price_history_points") or 0) > 0 else "unavailable",
                "status_label": "Đã có" if (coverage.get("price_history_points") or 0) > 0 else "Chưa đủ",
                "description": "Đã có chuỗi giá gần nhất để đọc động lượng." if (coverage.get("price_history_points") or 0) > 0 else "Chuỗi giá chưa đủ để đánh giá động lượng.",
                "note": "Đã có chuỗi giá gần nhất để đọc động lượng." if (coverage.get("price_history_points") or 0) > 0 else "Chuỗi giá chưa đủ để đánh giá động lượng.",
            },
            {
                "label": "Báo cáo tài chính",
                "group": "Báo cáo tài chính",
                "status": self._coverage_code(coverage.get("financials_loaded") or coverage.get("financial_ratios_loaded")),
                "status_label": self._coverage_status(coverage.get("financials_loaded") or coverage.get("financial_ratios_loaded")),
                "description": self._financial_coverage_description(financial_periods, ratio_periods, financial_source),
                "note": self._financial_coverage_description(financial_periods, ratio_periods, financial_source),
            },
            {
                "label": "Bối cảnh thị trường",
                "group": "Bối cảnh thị trường",
                "status": self._coverage_code(coverage.get("market_context_loaded")),
                "status_label": self._coverage_status(coverage.get("market_context_loaded")),
                "description": "Có VN-Index, thanh khoản và trạng thái thị trường để đối chiếu." if coverage.get("market_context_loaded") else "Chưa đủ dữ liệu thị trường chung để đọc bối cảnh.",
                "note": "Có VN-Index, thanh khoản và trạng thái thị trường để đối chiếu." if coverage.get("market_context_loaded") else "Chưa đủ dữ liệu thị trường chung để đọc bối cảnh.",
            },
            {
                "label": "So sánh cùng ngành",
                "group": "So sánh cùng ngành",
                "status": self._coverage_code(coverage.get("peer_context_loaded")),
                "status_label": self._coverage_status(coverage.get("peer_context_loaded")),
                "description": "Có doanh nghiệp cùng ngành để so sánh tương quan." if coverage.get("peer_context_loaded") else "Cần thêm peer định lượng đáng tin cậy.",
                "note": "Có doanh nghiệp cùng ngành để so sánh tương quan." if coverage.get("peer_context_loaded") else "Cần thêm peer định lượng đáng tin cậy.",
            },
            {
                "label": "Tin tức/nghiên cứu",
                "group": "Tin tức/nghiên cứu",
                "status": "available" if (coverage.get("external_research_items") or 0) > 0 else "unavailable",
                "status_label": "Đã có" if (coverage.get("external_research_items") or 0) > 0 else "Chưa đủ",
                "description": "Đã có tin tức/nghiên cứu phù hợp để bổ sung bối cảnh." if (coverage.get("external_research_items") or 0) > 0 else "Chưa có đủ tin tức/nghiên cứu phù hợp trong lần chạy này.",
                "note": "Đã có tin tức/nghiên cứu phù hợp để bổ sung bối cảnh." if (coverage.get("external_research_items") or 0) > 0 else "Chưa có đủ tin tức/nghiên cứu phù hợp trong lần chạy này.",
            },
            {
                "label": "Danh sách theo dõi",
                "group": "Danh sách theo dõi",
                "status": self._coverage_code(coverage.get("watchlist_loaded", True)),
                "status_label": self._coverage_status(coverage.get("watchlist_loaded", True)),
                "description": "Đã dùng watchlists để xác minh quyền phân tích mã cổ phiếu.",
                "note": "Đã dùng watchlists để xác minh quyền phân tích mã cổ phiếu.",
            },
        ]
        return rows

    def _coverage_status(self, value: Any) -> str:
        if value is True:
            return "Đã có"
        if value is False:
            return "Chưa đủ"
        return "Cần kiểm tra"

    def _coverage_code(self, value: Any) -> str:
        if value is True:
            return "available"
        if value is False:
            return "unavailable"
        return "partial"

    def _financial_source_label(self, summary: dict[str, Any]) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        source = bctc.get("source")
        if source:
            return self._source_display(source)
        text = " ".join(self._string_list(summary.get("data_quality_notes")) + self._string_list(summary.get("technical_data_quality_notes"))).lower()
        if "vietstock finance" in text:
            return "Vietstock Finance"
        if "cafef" in text:
            return "CafeF"
        if self._dict(summary.get("data_coverage")).get("analysis_data_loaded"):
            return "dữ liệu hệ thống đã xác thực"
        return "dữ liệu đã xác thực"

    def _financial_coverage_description(self, financial_periods: Any, ratio_periods: Any, source: str) -> str:
        full_count = int(financial_periods or 0)
        ratio_count = int(ratio_periods or 0)
        if full_count > 0:
            return f"Có {full_count} kỳ BCTC đầy đủ; nguồn chính: {source}."
        if ratio_count > 0:
            return f"Có {ratio_count} kỳ chỉ số tài chính; nguồn chính: {source}."
        return "Chưa đủ kỳ BCTC có thể chuẩn hóa để phân tích xu hướng tài chính."

    def _first_value(self, data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, "", {}, []):
                return data[key]
        return None

    def _value(self, value: Any) -> str:
        if value is None or value == "":
            return "Chưa xác minh"
        if isinstance(value, float):
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    def _compact_number(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "Chưa xác minh"
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:,.1f} tỷ"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:,.1f} triệu"
        if abs(value) >= 1_000:
            return f"{value / 1_000:,.1f} nghìn"
        return self._value(value)

    def _compact_money(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "Chưa xác minh"
        return f"{value / 1_000:,.1f} tỷ đồng" if abs(value) >= 1_000 else f"{value:,.1f} tỷ đồng"

    def _format_index_value(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "Chưa xác minh"
        return f"{value:,.2f}".rstrip("0").rstrip(".")

    def _format_percent(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "Chưa xác minh"
        formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
        return f"{formatted}%"

    def _format_liquidity(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "Chưa xác minh"
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:,.1f} tỷ cp"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:,.1f} triệu cp"
        if abs(value) >= 1_000:
            return f"{value / 1_000:,.1f} nghìn cp"
        return f"{value:,.0f} cp"

    def _format_trading_value_billion(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "Chưa xác minh"
        return f"{value:,.1f} tỷ đồng"

    def _market_regime_label(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text == "risk_on":
            return "Khá tích cực"
        if text == "risk_off":
            return "Thận trọng"
        if text in {"positive", "bullish", "tích cực", "kha tich cuc", "khá tích cực"}:
            return "Khá tích cực"
        if text in {"neutral", "trung tính", "trung tinh"}:
            return "Trung tính"
        if text in {"negative", "bearish", "thận trọng", "than trong"}:
            return "Thận trọng"
        if text:
            return str(value)
        return "Chưa xác minh"

    def _normalize_market_health_score(self, raw_score: Any, score_direction: str = "higher_is_better") -> int | None:
        if raw_score in (None, "") or isinstance(raw_score, bool):
            return None
        try:
            numeric = float(str(raw_score).replace("%", "").replace(",", ".").strip())
        except (TypeError, ValueError):
            return None
        if numeric != numeric:
            return None
        if 0 <= numeric <= 1:
            numeric *= 100
        if str(score_direction or "").lower() in {"higher_is_risk", "higher_is_worse", "higher_is_bad", "risk", "riskier_is_higher"}:
            numeric = 100 - numeric
        return max(0, min(100, int(round(numeric))))

    def _source_display(self, value: Any) -> str:
        text = str(value or "").strip()
        mapping = {
            "vietstock": "Vietstock",
            "vietstock_via_google_news_rss": "Vietstock",
            "cafef": "CafeF",
            "cafef company overview": "CafeF thông tin doanh nghiệp",
            "cafef thông tin doanh nghiệp": "CafeF thông tin doanh nghiệp",
            "cafef_via_google_news_rss": "CafeF",
            "google_news_rss": "Google News",
            "google news rss": "Google News",
            "mongo:test": "Dữ liệu nội bộ",
        }
        return mapping.get(text.lower(), text or "Chưa xác minh")

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _text(self, value: Any, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

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
