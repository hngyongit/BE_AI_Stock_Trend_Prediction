from __future__ import annotations

import math
import re
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.services.presentation_contract import display_percent_value, normalize_percent_score
from analyse.services.report_presentation_contract_service import ReportPresentationContractService
from analyse.services.stock_data_service import StockDataService


MISSING_DISPLAY = "Chưa xác minh"
AVAILABLE_STATUS = "available"
AVAILABLE_LABEL = "Đã ghi nhận"
MISSING_STATUS = "missing"
MISSING_LABEL = "Chưa xác minh"


class ReportPresentationNormalizer:
    """Build user-facing report presentation contracts from normalized summary data."""

    def __init__(self, stock_data_service: StockDataService | None = None, settings: Settings | None = None) -> None:
        self.stock_data_service = stock_data_service or StockDataService()
        self.settings = settings or get_settings()
        self.contract_service = ReportPresentationContractService()
        self.mapping_warnings: list[str] = []

    def normalize(self, summary: dict[str, Any], presentation: dict[str, Any] | None = None) -> dict[str, Any]:
        self.mapping_warnings = []
        result = dict(presentation or {})
        result["quick_overview"] = self.build_quick_overview(summary, result)
        result["market_context_view"] = self.build_market_context_view(summary, result.get("market_context_view"))
        result["financial_table"] = self.build_financial_table(summary)
        result["action_table"] = self.build_action_table(summary)
        result["scenario_table"] = self.build_scenario_table(summary)
        result["checklist"] = self.build_checklist(summary, result)
        result["data_coverage"] = self.build_data_coverage(summary)
        result["coverage_rows"] = result["data_coverage"]["items"]
        result["source_backed_enrichment"] = self._source_backed_enrichment_policy()

        self._sync_legacy_fields(summary, result)
        result = self.contract_service.normalize_and_validate(result, summary=summary)
        self._sync_legacy_fields(summary, result)
        return result

    def build_quick_overview(self, summary: dict[str, Any], presentation: dict[str, Any] | None = None) -> dict[str, Any]:
        latest = self._dict(summary.get("latest_market"))
        scores = self._dict(summary.get("scores"))
        coverage = self._dict(summary.get("data_coverage"))
        momentum = self._dict(summary.get("momentum"))
        chart_change = self._number(momentum.get("chart_period_change_pct"), momentum.get("change_pct"))
        chart_points = self._int(momentum.get("chart_points"), momentum.get("period_points"))
        chart_label = self._text(momentum.get("chart_period_label"), "Kỳ chart")
        financial_count = self._int(coverage.get("financial_periods_count"))
        confidence = normalize_percent_score(scores.get("score_confidence"))

        chart_missing_reason = self._chart_missing_reason(momentum, chart_points)
        chart_card = self._card(
            "Biến động kỳ chart",
            self._format_signed_percent(chart_change) if chart_change is not None else chart_missing_reason,
            raw_value=chart_change,
            status=AVAILABLE_STATUS if chart_change is not None else MISSING_STATUS,
            source="Dữ liệu giá và thanh khoản",
        )
        chart_card["chart_period_label"] = chart_label
        chart_card["chart_points"] = chart_points

        cards = [
            self._card("Giá", self._value(latest.get("close_price") or latest.get("close")), raw_value=latest.get("close_price") or latest.get("close")),
            chart_card,
            self._card("Điểm tổng", self._value(scores.get("overall_score")), raw_value=scores.get("overall_score")),
            self._card("Rủi ro", self._value(scores.get("risk_label")), raw_value=scores.get("risk_score")),
            self._card(
                "Số kỳ BCTC",
                f"{financial_count} kỳ" if financial_count else MISSING_DISPLAY,
                raw_value=financial_count,
                status=AVAILABLE_STATUS if financial_count else MISSING_STATUS,
                source=self._financial_source(summary),
            ),
            self._card(
                "Tỷ lệ tin cậy dữ liệu",
                f"{confidence}%" if confidence is not None else MISSING_DISPLAY,
                raw_value=confidence,
                status=AVAILABLE_STATUS if confidence is not None else MISSING_STATUS,
            ),
        ]

        bar = self._dict((presentation or {}).get("summary_bar"))
        bar.update(
            {
                "latest_price": latest.get("close_price") or latest.get("close"),
                "chart_return": chart_change,
                "chart_period_change_pct": chart_change,
                "chart_period_label": chart_label,
                "chart_points": chart_points,
                "overall_score": scores.get("overall_score"),
                "risk_label": scores.get("risk_label"),
                "financial_periods_count": financial_count,
                "data_confidence": confidence,
                "data_confidence_display": display_percent_value(scores.get("score_confidence")),
            }
        )

        return {
            "title": "Tổng quan nhanh",
            "status": AVAILABLE_STATUS,
            "cards": cards,
            "summary_bar": bar,
            "chart_period_change_pct": chart_change,
            "chart_period_label": chart_label,
            "chart_period_start_price": momentum.get("chart_period_start_price") or momentum.get("first_close"),
            "chart_period_end_price": momentum.get("chart_period_end_price") or momentum.get("last_close"),
            "chart_points": chart_points,
        }

    def build_market_context_view(self, summary: dict[str, Any], existing: Any) -> dict[str, Any]:
        view = dict(existing) if isinstance(existing, dict) else {}
        market = self._dict(summary.get("hose_market_context"))
        market_debug = self._dict(summary.get("market_context_debug"))
        normalized = self._dict(market_debug.get("normalized"))
        trading_value = self._number(
            view.get("trading_value_billion"),
            normalized.get("trading_value_billion"),
            market.get("trading_value_billion"),
            market.get("tradingValueBillion"),
            market.get("total_value"),
            market.get("totalValue"),
            market.get("totalTradingValue"),
            market.get("total_trading_value"),
            market.get("market_value"),
            market.get("marketValue"),
            market.get("value_billion"),
            market.get("valueBillion"),
            market.get("liquidity_value"),
            market.get("liquidityValue"),
            market.get("matched_value"),
            market.get("matchedValue"),
        )
        if trading_value is None:
            trading_value = self._parse_trading_value_from_text(view.get("narrative") or view.get("summary"))
            if trading_value is not None:
                self.mapping_warnings.append("market_context_view.cards.trading_value recovered_from_narrative")

        cards = []
        existing_cards = view.get("cards") if isinstance(view.get("cards"), list) else []
        by_label = {str(card.get("label")): dict(card) for card in existing_cards if isinstance(card, dict)}
        labels = ["Chỉ số", "Biến động", "Thanh khoản", "Giá trị giao dịch", "Trạng thái", "Điểm sức khỏe thị trường"]
        for label in labels:
            card = by_label.get(label, {"label": label, "value": MISSING_DISPLAY})
            if label == "Giá trị giao dịch" and trading_value is not None:
                card["value"] = self._format_trading_value_billion(trading_value)
                card["raw_value"] = trading_value
                card["trading_value_billion"] = trading_value
            status = AVAILABLE_STATUS if card.get("value") not in (None, "", MISSING_DISPLAY) else MISSING_STATUS
            card["status"] = status
            card["status_label"] = AVAILABLE_LABEL if status == AVAILABLE_STATUS else MISSING_LABEL
            cards.append(card)

        if trading_value is not None:
            view["trading_value_billion"] = trading_value
            view["trading_value_display"] = self._format_trading_value_billion(trading_value)
        view["cards"] = cards
        return view

    def build_financial_table(self, summary: dict[str, Any]) -> dict[str, Any]:
        bctc = self._dict(summary.get("bctc_3q"))
        periods = [dict(item) for item in self._list(bctc.get("periods"))[:3]]
        period_count = len(periods)
        source = self._financial_source(summary)
        if not periods:
            return {
                "title": "Bảng tài chính 3 quý",
                "status": MISSING_STATUS,
                "status_label": MISSING_LABEL,
                "source": source,
                "period_count": 0,
                "columns": [],
                "rows": [],
                "missing_reason": "Chưa có kỳ BCTC đủ chỉ tiêu định lượng để dựng bảng.",
            }

        is_bank = any(self.stock_data_service.looks_like_bank_period(period) for period in periods)
        metric_defs = self._bank_metrics() if is_bank else self._non_bank_metrics()
        rows = []
        for label, key in metric_defs:
            raw_values = [self._valid_financial_value(period, key) for period in periods]
            if not any(value is not None for value in raw_values):
                continue
            rows.append(
                {
                    "metric": label,
                    "key": key,
                    "values": [self._value(value) if value is not None else MISSING_DISPLAY for value in raw_values],
                    "raw_values": raw_values,
                    "cell_statuses": [AVAILABLE_STATUS if value is not None else MISSING_STATUS for value in raw_values],
                }
            )

        status = AVAILABLE_STATUS if rows else MISSING_STATUS
        return {
            "title": "Bảng tài chính 3 quý",
            "status": status,
            "status_label": AVAILABLE_LABEL if status == AVAILABLE_STATUS else MISSING_LABEL,
            "source": source,
            "period_count": period_count,
            "columns": ["Chỉ tiêu", *[self._text(period.get("period"), f"Kỳ {idx + 1}") for idx, period in enumerate(periods)]],
            "rows": rows,
            "is_bank": is_bank,
            "missing_reason": "" if rows else "Các kỳ BCTC có mặt nhưng chưa có chỉ tiêu phù hợp để hiển thị.",
        }

    def build_action_table(self, summary: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for source in self._action_sources(summary):
            rows.extend(self._action_rows_from_source(source))
        if not rows:
            rows = self._fallback_action_rows(summary) if self.settings.report_allow_safe_action_fallback else []
        rows = [self._complete_action_row(row, summary) for row in rows]
        rows = self._dedupe_rows(
            [self._sanitize_action_row(row) for row in rows],
            ("timeframe", "action", "condition", "price_zone", "position_size", "stop_loss", "note"),
        )[:6]
        status = AVAILABLE_STATUS if rows else MISSING_STATUS
        return {
            "title": "Kế hoạch hành động",
            "status": status,
            "status_label": AVAILABLE_LABEL if status == AVAILABLE_STATUS else MISSING_LABEL,
            "rows": rows,
            "missing_reason": "" if rows else "Chưa có đủ điểm số, rủi ro hoặc watchpoints để dựng bảng theo dõi.",
        }

    def build_scenario_table(self, summary: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for source in self._scenario_sources(summary):
            rows.extend(self._scenario_rows_from_source(source))
        if not rows:
            rows = self._fallback_scenario_rows(summary) if self.settings.report_allow_safe_scenario_fallback else []
        rows = self._dedupe_rows(rows, ("scenario", "condition", "expected_behavior", "risk", "probability_pct", "time_horizon"))[:5]
        status = AVAILABLE_STATUS if rows else MISSING_STATUS
        return {
            "title": "Kịch bản",
            "status": status,
            "status_label": AVAILABLE_LABEL if status == AVAILABLE_STATUS else MISSING_LABEL,
            "rows": rows,
            "missing_reason": "" if rows else "Chưa có dữ liệu xu hướng, rủi ro hoặc điểm số để dựng ma trận kịch bản.",
        }

    def build_checklist(self, summary: dict[str, Any], presentation: dict[str, Any] | None = None) -> dict[str, Any]:
        items = []
        for source in self._checklist_sources(summary, presentation):
            items.extend(self._checklist_items_from_source(source))
        if not items:
            items = self._fallback_checklist_items(summary) if self.settings.report_allow_safe_checklist_fallback else []
        items = self._dedupe_rows(items, ("label", "note"))[:8]
        status = AVAILABLE_STATUS if items else MISSING_STATUS
        return {
            "title": "Checklist",
            "status": status,
            "status_label": AVAILABLE_LABEL if status == AVAILABLE_STATUS else MISSING_LABEL,
            "items": items,
            "missing_reason": "" if items else "Chưa có watchpoints, risk management, signals hoặc checks để dựng checklist.",
        }

    def build_data_coverage(self, summary: dict[str, Any]) -> dict[str, Any]:
        coverage = self._dict(summary.get("data_coverage"))
        peers = self._list(self._dict(summary.get("industry_peer_context")).get("peers"))
        financial_count = self._int(coverage.get("financial_periods_count"))
        price_points = self._int(coverage.get("price_history_points"))
        news_count = self._int(coverage.get("external_research_items"))
        peer_count = len(peers)
        items = [
            self._coverage_item(
                "market_data",
                "Giá và thanh khoản",
                bool(coverage.get("latest_price_loaded")),
                "Đã ghi nhận",
                "Chưa đủ giá/khối lượng mới nhất",
                "Đã có giá, khối lượng và chỉ tiêu giao dịch gần nhất." if coverage.get("latest_price_loaded") else "Chưa đủ giá/khối lượng mới nhất để đọc thanh khoản.",
            ),
            self._coverage_count_item("price_history", "Chuỗi giá", price_points, "điểm dữ liệu", "Chuỗi giá dùng để tính biến động kỳ chart."),
            self._coverage_count_item("financials", "BCTC", financial_count, "kỳ", "Có kỳ BCTC dùng cho phân tích.", source=self._financial_source(summary)),
            self._cafef_financial_coverage_item(summary),
            self._coverage_item(
                "market_context",
                "Bối cảnh VNINDEX/HoSE",
                bool(coverage.get("market_context_loaded")),
                "Có dữ liệu",
                "Chưa đủ dữ liệu",
                "Có VN-Index, thanh khoản và trạng thái thị trường để đối chiếu." if coverage.get("market_context_loaded") else "Chưa đủ dữ liệu thị trường chung để đọc bối cảnh.",
            ),
            self._coverage_count_item("peers", "Peer cùng ngành", peer_count, "peer", "Có mã peer cùng ngành để phục vụ so sánh."),
            self._coverage_count_item("external_news", "Tin tức bên ngoài", news_count, "tin", "Có tin tức/nghiên cứu phù hợp để bổ sung bối cảnh."),
            self._coverage_item(
                "watchlist",
                "Watchlist",
                bool(coverage.get("watchlist_loaded")),
                "Đã xác minh quyền phân tích",
                "Chưa xác minh quyền phân tích",
                "Đã dùng watchlists để xác minh quyền phân tích mã cổ phiếu." if coverage.get("watchlist_loaded") else "Chưa xác minh được quyền phân tích từ watchlists.",
            ),
        ]
        items = [item for item in items if item]
        return {"title": "Độ phủ dữ liệu", "items": items}

    def build_debug_payloads(self, summary: dict[str, Any], presentation: dict[str, Any], final_response: dict[str, Any] | None = None) -> dict[str, Any]:
        coverage = self._dict(summary.get("data_coverage"))
        market_debug = self._dict(summary.get("market_context_debug"))
        return {
            "quick_overview": {
                "raw_fields_found": self._summary_keys(summary, ("price_history", "momentum", "latest_market", "data_coverage")),
                "normalized": self._dict(summary.get("momentum")),
                "presentation": self._dict(presentation.get("quick_overview")),
                "missing_fields": self._missing_quick_fields(presentation),
                "mapping_warnings": self.mapping_warnings,
            },
            "market_context": {
                "raw_fields_found": market_debug.get("raw_keys_found") or [],
                "normalized": market_debug.get("normalized") or summary.get("hose_market_context") or {},
                "presentation": self._dict(presentation.get("market_context_view")),
                "missing_fields": market_debug.get("missing_fields") or [],
                "mapping_warnings": self.mapping_warnings,
            },
            "financial_table": {
                "raw_fields_found": self._summary_keys(summary, ("bctc_3q", "financial_balance", "data_coverage")),
                "normalized": {"period_count": coverage.get("financial_periods_count"), "periods": self._list(self._dict(summary.get("bctc_3q")).get("periods"))[:3]},
                "presentation": self._dict(presentation.get("financial_table")),
                "missing_fields": [] if self._dict(presentation.get("financial_table")).get("rows") else ["financial_table.rows"],
                "mapping_warnings": self.mapping_warnings,
            },
            "action_scenario_checklist": {
                "raw_fields_found": self._summary_keys(summary, ("action_plan", "investment_plan", "scenarios", "scenario_matrix", "checklist", "watch_points", "risk_management")),
                "normalized": {
                    "action_table_rows": len(self._list(self._dict(presentation.get("action_table")).get("rows"))),
                    "scenario_table_rows": len(self._list(self._dict(presentation.get("scenario_table")).get("rows"))),
                    "checklist_items": len(self._list(self._dict(presentation.get("checklist")).get("items"))),
                },
                "presentation": {
                    "action_table": presentation.get("action_table"),
                    "scenario_table": presentation.get("scenario_table"),
                    "checklist": presentation.get("checklist"),
                },
                "missing_fields": self._missing_action_fields(presentation),
                "mapping_warnings": self.mapping_warnings,
            },
            "data_coverage_sources": {
                "raw_fields_found": self._summary_keys(summary, ("data_coverage", "industry_peer_context", "external_research_context")),
                "normalized": coverage,
                "presentation": self._dict(presentation.get("data_coverage")),
                "missing_fields": [],
                "mapping_warnings": self.mapping_warnings,
            },
            "audit": self.build_mapping_audit(summary, presentation, final_response),
        }

    def build_mapping_audit(self, summary: dict[str, Any], presentation: dict[str, Any], final_response: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        quick = self._dict(presentation.get("quick_overview"))
        market = self._dict(presentation.get("market_context_view"))
        financial = self._dict(presentation.get("financial_table"))
        action = self._dict(presentation.get("action_table"))
        scenario = self._dict(presentation.get("scenario_table"))
        checklist = self._dict(presentation.get("checklist"))
        coverage = self._dict(presentation.get("data_coverage"))
        final_presentation = self._dict(self._dict(self._dict(final_response or {}).get("data")).get("summary")).get("report_presentation")
        return [
            self._audit_row("quick_overview.cards.chart_period_change", bool(summary.get("price_history")), bool(summary.get("momentum")), bool(quick), self._card_available(quick, "Biến động kỳ chart"), final_presentation),
            self._audit_row("market_context_view.cards.trading_value", bool(summary.get("hose_market_context")), bool(self._dict(summary.get("market_context_debug")).get("normalized")), bool(market), self._card_available(market, "Giá trị giao dịch"), final_presentation),
            self._audit_row("financial_table.rows", bool(self._list(self._dict(summary.get("bctc_3q")).get("periods"))), bool(self._list(self._dict(summary.get("bctc_3q")).get("periods"))), bool(financial), bool(financial.get("rows")), final_presentation),
            self._audit_row("action_table.rows", bool(self._action_sources(summary)), True, bool(action), bool(action.get("rows")), final_presentation),
            self._audit_row("scenario_table.rows", bool(self._scenario_sources(summary)), True, bool(scenario), bool(scenario.get("rows")), final_presentation),
            self._audit_row("checklist.items", bool(self._checklist_sources(summary, presentation)), True, bool(checklist), bool(checklist.get("items")), final_presentation),
            self._audit_row("data_coverage.items", bool(summary.get("data_coverage")), bool(summary.get("data_coverage")), bool(coverage), bool(coverage.get("items")), final_presentation),
        ]

    def _sync_legacy_fields(self, summary: dict[str, Any], presentation: dict[str, Any]) -> None:
        quick = self._dict(presentation.get("quick_overview"))
        presentation["summary_bar"] = quick.get("summary_bar") or presentation.get("summary_bar") or {}

        action_rows = self._list(self._dict(presentation.get("action_table")).get("rows"))
        plan = dict(self._dict(summary.get("investment_plan")))
        plan["action_table"] = [
            {
                "time": row.get("timeframe"),
                "action": row.get("action"),
                "condition": row.get("condition") or row.get("trigger"),
                "trigger": row.get("trigger") or row.get("condition"),
                "price_zone": row.get("price_zone"),
                "price_zone_note": row.get("price_zone_note"),
                "position_size": row.get("position_size"),
                "position_size_note": row.get("position_size_note"),
                "stop_loss": row.get("stop_loss"),
                "note": row.get("note"),
                "risk_note": row.get("risk_note"),
                "source_basis": row.get("source_basis"),
            }
            for row in action_rows
        ]
        summary["investment_plan"] = plan

        scenario_rows = self._list(self._dict(presentation.get("scenario_table")).get("rows"))
        summary["scenario_matrix"] = [
            {
                "scenario": row.get("scenario"),
                "probability_pct": row.get("probability_pct"),
                "time_horizon": row.get("time_horizon"),
                "condition": row.get("condition"),
                "response": row.get("expected_behavior"),
                "supporting_signals": row.get("supporting_signals"),
                "invalidation_signals": row.get("invalidation_signals"),
                "risk": row.get("risk"),
                "risk_note": row.get("risk_note"),
            }
            for row in scenario_rows
        ]
        summary["checklist"] = self._list(self._dict(presentation.get("checklist")).get("items"))

    def _card(self, label: str, value: Any, *, raw_value: Any = None, status: str | None = None, source: str | None = None) -> dict[str, Any]:
        computed_status = status or (AVAILABLE_STATUS if value not in (None, "", MISSING_DISPLAY) else MISSING_STATUS)
        item = {
            "label": label,
            "value": value,
            "raw_value": raw_value,
            "status": computed_status,
            "status_label": AVAILABLE_LABEL if computed_status == AVAILABLE_STATUS else MISSING_LABEL,
        }
        if source:
            item["source"] = source
        return item

    def _coverage_item(self, key: str, title: str, available: bool, available_value: str, missing_value: str, description: str, *, source: str | None = None) -> dict[str, Any]:
        status = AVAILABLE_STATUS if available else MISSING_STATUS
        value = available_value if available else missing_value
        item = {
            "key": key,
            "title": title,
            "label": title,
            "group": title,
            "status": status,
            "status_label": AVAILABLE_LABEL if available else MISSING_LABEL,
            "value": value,
            "description": description,
            "note": description,
        }
        if source:
            item["source"] = source
        return self._fix_available_coverage_value(item)

    def _coverage_count_item(self, key: str, title: str, count: int, unit: str, description: str, *, source: str | None = None) -> dict[str, Any]:
        available = count > 0
        value = f"{count} {unit}" if available else MISSING_DISPLAY
        return self._coverage_item(key, title, available, value, MISSING_DISPLAY, description if available else f"{title} chưa đủ dữ liệu trong lần chạy này.", source=source)

    def _fix_available_coverage_value(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("status") == AVAILABLE_STATUS and item.get("value") in (None, "", MISSING_DISPLAY):
            item["value"] = item.get("status_label") or AVAILABLE_LABEL
        return item

    def _cafef_financial_coverage_item(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        contribution = self._dict(summary.get("cafef_financial_contribution"))
        if not contribution:
            return None
        status = self._text(contribution.get("status"), "insufficient")
        filled_count = self._int(contribution.get("filled_fields_count"))
        metrics_count = self._int(contribution.get("metrics_count"))
        periods_count = self._int(contribution.get("periods_count"))
        if status == "success" and filled_count:
            value = f"Bổ sung {filled_count} chỉ tiêu"
            description = "CafeF đã được dùng để bù dữ liệu tài chính còn thiếu."
        elif status == "partial" and metrics_count:
            value = f"Đối chiếu {metrics_count} chỉ tiêu"
            description = "CafeF cung cấp dữ liệu tài chính để đối chiếu, nhưng chưa bù thêm field còn thiếu."
        elif status in {"failed", "disabled", "skipped"}:
            value = "Chưa dùng"
            description = "CafeF tài chính chưa được dùng trong lần chạy này."
        else:
            value = "Chưa đủ dữ liệu"
            description = "CafeF chưa cung cấp đủ chỉ tiêu tài chính có thể chuẩn hóa trong lần chạy này."
        return {
            "key": "cafef_financial",
            "title": "CafeF tài chính",
            "label": "CafeF tài chính",
            "group": "CafeF tài chính",
            "status": status if status in {"success", "partial", "insufficient", "failed", "disabled", "skipped"} else "insufficient",
            "status_label": self._status_label(status),
            "value": value,
            "raw_value": filled_count or metrics_count or periods_count,
            "description": description,
            "note": description,
            "source": "CafeF tài chính",
        }

    def _action_sources(self, summary: dict[str, Any]) -> list[Any]:
        plan = self._dict(summary.get("investment_plan"))
        candidates = [
            summary.get("action_table"),
            summary.get("action_plan"),
            summary.get("actionPlan"),
            summary.get("monitoring_plan"),
            summary.get("monitoringPlan"),
            plan.get("action_table"),
            {
                "short_term": summary.get("short_term") or summary.get("shortTerm"),
                "medium_term": summary.get("medium_term") or summary.get("mediumTerm"),
                "watch_points": summary.get("watch_points") or summary.get("watchPoints"),
                "risk_management": summary.get("risk_management") or summary.get("riskManagement"),
            },
        ]
        return [item for item in candidates if item not in (None, "", {}, [])]

    def _action_rows_from_source(self, source: Any) -> list[dict[str, Any]]:
        if isinstance(source, list):
            return [self._action_row_from_item(item, "Theo dõi") for item in source]
        if not isinstance(source, dict):
            return []
        rows: list[dict[str, Any]] = []
        if isinstance(source.get("rows"), list):
            rows.extend(self._action_row_from_item(item, "Theo dõi") for item in source["rows"])
        for key, timeframe in (
            ("short_term", "Ngắn hạn"),
            ("shortTerm", "Ngắn hạn"),
            ("medium_term", "Trung hạn"),
            ("mediumTerm", "Trung hạn"),
            ("watch_points", "Điểm cần theo dõi"),
            ("watchPoints", "Điểm cần theo dõi"),
            ("risk_management", "Quản trị rủi ro"),
            ("riskManagement", "Quản trị rủi ro"),
        ):
            value = source.get(key)
            if isinstance(value, list):
                rows.extend(self._action_row_from_item(item, timeframe) for item in value)
            elif value:
                rows.append(self._action_row_from_item(value, timeframe))
        return [row for row in rows if row.get("action")]

    def _action_row_from_item(self, item: Any, timeframe: str) -> dict[str, Any]:
        if isinstance(item, dict):
            return {
                "timeframe": self._text(item.get("timeframe") or item.get("time") or item.get("horizon"), timeframe),
                "action": self._text(item.get("action") or item.get("task") or item.get("note") or item.get("content"), ""),
                "trigger": self._text(item.get("trigger") or item.get("condition") or item.get("signal"), "Giá/khối lượng hoặc dữ liệu mới xác nhận."),
                "condition": self._text(item.get("condition") or item.get("trigger") or item.get("signal"), "Giá/khối lượng hoặc dữ liệu mới xác nhận."),
                "price_zone": self._text(item.get("price_zone") or item.get("priceZone") or item.get("zone") or item.get("reference_level"), ""),
                "price_zone_note": self._text(item.get("price_zone_note") or item.get("priceZoneNote"), ""),
                "position_size": self._text(item.get("position_size") or item.get("positionSize") or item.get("allocation") or item.get("weight"), ""),
                "position_size_note": self._text(item.get("position_size_note") or item.get("positionSizeNote"), ""),
                "stop_loss": self._text(item.get("stop_loss") or item.get("stopLoss") or item.get("risk_limit") or item.get("guardrail"), ""),
                "note": self._text(item.get("note") or item.get("comment") or item.get("risk_note") or item.get("risk") or item.get("guardrail"), ""),
                "risk_note": self._text(item.get("risk_note") or item.get("risk") or item.get("guardrail"), "Không tăng rủi ro khi dữ liệu chưa xác nhận."),
                "source_basis": self._text(item.get("source_basis") or item.get("sourceBasis") or item.get("source"), ""),
            }
        return {
            "timeframe": timeframe,
            "action": self._text(item, ""),
            "trigger": "Dữ liệu mới hoặc tín hiệu giá/khối lượng xác nhận.",
            "condition": "Dữ liệu mới hoặc tín hiệu giá/khối lượng xác nhận.",
            "price_zone": "",
            "price_zone_note": "",
            "position_size": "",
            "position_size_note": "",
            "stop_loss": "",
            "note": "",
            "risk_note": "Giữ kỷ luật quản trị rủi ro và không xem đây là khuyến nghị cá nhân hóa.",
            "source_basis": "",
        }

    def _complete_action_row(self, row: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        completed = dict(row)
        plan = self._dict(summary.get("investment_plan"))
        position = self._dict(plan.get("position_sizing"))
        max_position = self._number(position.get("max_position_pct"), self.settings.default_max_position_pct)
        risk_pct = self._number(position.get("risk_per_trade_pct"), self.settings.default_risk_per_trade_pct)
        completed["condition"] = self._text(completed.get("condition") or completed.get("trigger"), "Chuỗi giá hoặc điểm động lượng có tín hiệu xác nhận rõ hơn.")
        completed["trigger"] = completed["condition"]
        completed["price_zone"] = self._text(
            completed.get("price_zone"),
            "Theo vùng giá hiện tại; chờ xác nhận hỗ trợ/kháng cự nếu dữ liệu chưa có.",
        )
        completed["price_zone_note"] = self._text(
            completed.get("price_zone_note"),
            "Dùng vùng giá hiện tại làm mốc quan sát nếu chưa có vùng hỗ trợ/kháng cự đáng tin cậy.",
        )
        completed["position_size"] = self._text(
            completed.get("position_size"),
            f"Không vượt quá {self._format_plain_percent(max_position)} danh mục giả định.",
        )
        completed["position_size_note"] = self._text(
            completed.get("position_size_note"),
            f"Không vượt quá {self._format_plain_percent(max_position)} danh mục giả định nếu chỉ dùng cho mô phỏng.",
        )
        completed["stop_loss"] = self._text(
            completed.get("stop_loss"),
            f"Theo nguyên tắc rủi ro {self._format_plain_percent(risk_pct)} vốn hoặc vùng hỗ trợ gần nhất nếu có dữ liệu.",
        )
        completed["note"] = self._text(
            completed.get("note") or completed.get("risk_note"),
            "Chỉ dùng làm khung theo dõi, không phải khuyến nghị mua/bán.",
        )
        completed["risk_note"] = self._text(
            completed.get("risk_note") or completed.get("note"),
            "Chỉ dùng làm khung theo dõi, không phải khuyến nghị mua/bán.",
        )
        completed["source_basis"] = self._text(completed.get("source_basis"), "Dữ liệu hiện có")
        return completed

    def _fallback_action_rows(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        scores = self._dict(summary.get("scores"))
        risks = self._string_list(summary.get("weaknesses"))
        momentum = self._dict(summary.get("momentum"))
        rows: list[dict[str, Any]] = []
        if momentum or scores:
            rows.append(
                {
                    "timeframe": "Ngắn hạn",
                    "action": "Theo dõi phản ứng giá và thanh khoản quanh vùng biến động gần nhất.",
                    "trigger": "Chuỗi giá hoặc điểm động lượng có tín hiệu xác nhận rõ hơn.",
                    "condition": "Chuỗi giá hoặc điểm động lượng có tín hiệu xác nhận rõ hơn.",
                    "price_zone": "Theo vùng giá hiện tại; chờ xác nhận hỗ trợ/kháng cự nếu dữ liệu chưa có.",
                    "note": "Chỉ dùng làm khung theo dõi, không phải khuyến nghị mua/bán.",
                    "risk_note": "Không tăng tỷ trọng khi thanh khoản suy yếu hoặc dữ liệu giá thiếu xác nhận.",
                }
            )
        if self._list(self._dict(summary.get("bctc_3q")).get("periods")) or risks:
            rows.append(
                {
                    "timeframe": "Trung hạn",
                    "action": "Kiểm tra lại BCTC, chất lượng lợi nhuận và các rủi ro đã nêu.",
                    "trigger": "Có BCTC mới, tin công bố chính thức hoặc thay đổi đáng kể trong điểm rủi ro.",
                    "condition": "Có BCTC mới, tin công bố chính thức hoặc thay đổi đáng kể trong điểm rủi ro.",
                    "price_zone": "Chờ xác nhận hỗ trợ/kháng cự từ dữ liệu giá mới.",
                    "note": "Ưu tiên kiểm chứng dữ liệu gốc trước khi thay đổi kế hoạch theo dõi.",
                    "risk_note": risks[0] if risks else "Ưu tiên dữ liệu đã xác thực thay vì suy diễn thêm.",
                }
            )
        return rows

    def _scenario_sources(self, summary: dict[str, Any]) -> list[Any]:
        candidates = [
            summary.get("scenario_table"),
            summary.get("forecast_scenarios"),
            summary.get("forecast_scenario_table"),
            summary.get("scenarios"),
            summary.get("scenario_matrix"),
            summary.get("scenarioMatrix"),
            {
                "bull": summary.get("bull"),
                "base": summary.get("base"),
                "bear": summary.get("bear"),
            },
        ]
        return [item for item in candidates if item not in (None, "", {}, [])]

    def _scenario_rows_from_source(self, source: Any) -> list[dict[str, Any]]:
        if isinstance(source, list):
            return [self._scenario_row_from_item(item, "") for item in source if isinstance(item, (dict, str))]
        if not isinstance(source, dict):
            return []
        rows: list[dict[str, Any]] = []
        if isinstance(source.get("rows"), list):
            rows.extend(self._scenario_row_from_item(item, "") for item in source["rows"])
        for key, label in (("bull", "Tích cực"), ("base", "Cơ sở"), ("bear", "Thận trọng")):
            if source.get(key):
                rows.append(self._scenario_row_from_item(source[key], label))
        return [row for row in rows if row.get("scenario")]

    def _scenario_row_from_item(self, item: Any, fallback_name: str) -> dict[str, Any]:
        if isinstance(item, dict):
            invalidations = self._string_list(item.get("invalidation_signals") or item.get("invalidationSignals"))
            supporting = self._string_list(item.get("supporting_signals") or item.get("supportingSignals"))
            risk_note = self._text(item.get("risk") or item.get("risk_note") or item.get("riskNote") or item.get("guardrail"), "Kết quả có thể thay đổi khi thị trường chung hoặc dữ liệu mới xấu đi.")
            return {
                "scenario": self._text(item.get("scenario") or item.get("name") or item.get("label"), fallback_name or "Kịch bản"),
                "probability_pct": self._int(item.get("probability_pct") or item.get("probabilityPct") or item.get("probability")),
                "time_horizon": self._text(item.get("time_horizon") or item.get("timeHorizon") or item.get("horizon"), "1-3 tháng"),
                "condition": self._text(item.get("condition") or item.get("trigger"), "Cần thêm dữ liệu xác nhận."),
                "expected_behavior": self._text(item.get("expected_behavior") or item.get("expectedBehavior") or item.get("response") or item.get("behavior"), "Theo dõi và đối chiếu lại dữ liệu."),
                "supporting_signals": supporting,
                "invalidation_signals": invalidations,
                "risk": risk_note,
                "risk_note": risk_note,
                "source_labels": self._string_list(item.get("source_labels") or item.get("sourceLabels")),
                "inference_basis": self._string_list(item.get("inference_basis") or item.get("inferenceBasis")),
            }
        return {
            "scenario": fallback_name or str(item),
            "probability_pct": None,
            "time_horizon": "1-3 tháng",
            "condition": str(item),
            "expected_behavior": "Theo dõi và chờ xác nhận từ dữ liệu mới.",
            "supporting_signals": [],
            "invalidation_signals": ["Dữ liệu mới làm luận điểm suy yếu."],
            "risk": "Không đảm bảo kết quả; cần quản trị rủi ro.",
            "risk_note": "Không đảm bảo kết quả; cần quản trị rủi ro.",
        }

    def _fallback_scenario_rows(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        scores = self._dict(summary.get("scores"))
        risk_label = self._text(scores.get("risk_label"), "rủi ro cần theo dõi")
        has_signal = bool(scores or summary.get("momentum") or summary.get("weaknesses"))
        if not has_signal:
            return []
        return [
            {
                "scenario": "Tích cực",
                "probability_pct": 30,
                "time_horizon": "1-3 tháng",
                "condition": "Giá giữ xu hướng và thanh khoản cải thiện cùng dữ liệu cơ bản không xấu đi.",
                "expected_behavior": "Động lượng có thể được củng cố, nhưng vẫn cần xác nhận bằng dữ liệu mới.",
                "supporting_signals": ["Điểm định lượng, momentum hoặc dữ liệu thị trường hiện có đang đủ để dựng khung quan sát."],
                "invalidation_signals": ["Giá giảm mạnh kèm thanh khoản cao.", "BCTC mới xấu hơn kỳ trước.", "Tin tiêu cực đáng tin cậy về doanh nghiệp/ngành."],
                "risk": "Tin xấu thị trường chung hoặc BCTC mới có thể làm suy yếu tín hiệu.",
                "risk_note": "Tin xấu thị trường chung hoặc BCTC mới có thể làm suy yếu tín hiệu.",
            },
            {
                "scenario": "Cơ sở",
                "probability_pct": 45,
                "time_horizon": "1-3 tháng",
                "condition": "Giá đi ngang, thanh khoản ổn định và điểm tổng chưa tạo xác nhận mạnh.",
                "expected_behavior": "Tiếp tục theo dõi, ưu tiên đối chiếu dữ liệu nguồn.",
                "supporting_signals": ["Kịch bản cơ sở được dựng từ điểm số, rủi ro và dữ liệu hiện có."],
                "invalidation_signals": ["Bối cảnh thị trường chuyển sang risk-off.", "Dữ liệu cơ bản mới thay đổi lớn."],
                "risk": f"Rủi ro hiện được ghi nhận là {risk_label}; thiếu động lực mới có thể làm tín hiệu nhiễu.",
                "risk_note": f"Rủi ro hiện được ghi nhận là {risk_label}; thiếu động lực mới có thể làm tín hiệu nhiễu.",
            },
            {
                "scenario": "Thận trọng",
                "probability_pct": 25,
                "time_horizon": "1-3 tháng",
                "condition": "Giá gãy vùng hỗ trợ gần nhất, thanh khoản suy yếu hoặc rủi ro dữ liệu tăng.",
                "expected_behavior": "Ưu tiên bảo toàn vốn và kiểm tra lại luận điểm.",
                "supporting_signals": ["Rủi ro dữ liệu hoặc rủi ro thị trường cần được theo dõi trước khi nâng conviction."],
                "invalidation_signals": ["Tín hiệu tích cực chỉ được khôi phục khi giá, thanh khoản và dữ liệu mới cùng xác nhận trở lại."],
                "risk": "Rủi ro giảm sâu hơn nếu thị trường chung chuyển sang phòng thủ.",
                "risk_note": "Rủi ro giảm sâu hơn nếu thị trường chung chuyển sang phòng thủ.",
            },
        ]

    def _checklist_sources(self, summary: dict[str, Any], presentation: dict[str, Any] | None = None) -> list[Any]:
        executive = self._dict((presentation or {}).get("executive_summary"))
        candidates = [
            summary.get("checklist"),
            summary.get("watch_points"),
            summary.get("watchPoints"),
            summary.get("risk_management"),
            summary.get("riskManagement"),
            summary.get("signals"),
            summary.get("risks"),
            summary.get("weaknesses"),
            executive.get("checks_before_action"),
        ]
        return [item for item in candidates if item not in (None, "", {}, [])]

    def _checklist_items_from_source(self, source: Any) -> list[dict[str, Any]]:
        if isinstance(source, list):
            return [self._checklist_item_from_value(item) for item in source]
        if isinstance(source, dict):
            if isinstance(source.get("items"), list):
                return [self._checklist_item_from_value(item) for item in source["items"]]
            return [self._checklist_item_from_value(value) for value in source.values() if value]
        return [self._checklist_item_from_value(source)]

    def _checklist_item_from_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            label = self._text(value.get("label") or value.get("title") or value.get("item"), "Kiểm tra dữ liệu")
            note = self._text(value.get("note") or value.get("description") or value.get("risk") or value.get("content"), "Đối chiếu với nguồn dữ liệu gốc.")
            status = self._text(value.get("status"), "pending")
            source_basis = self._text(value.get("source_basis") or value.get("sourceBasis") or value.get("source"), "Dữ liệu hiện có")
            return {"label": label, "status": status, "note": note, "source_basis": source_basis}
        text = self._text(value, "Đối chiếu dữ liệu nguồn.")
        return {"label": self._checklist_label(text), "status": "pending", "note": text, "source_basis": "Dữ liệu hiện có"}

    def _fallback_checklist_items(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        items = []
        if summary.get("momentum"):
            items.append({"label": "Kiểm tra xu hướng giá", "status": "pending", "note": "Đối chiếu biến động kỳ chart với thanh khoản và vùng hỗ trợ/kháng cự."})
        if self._list(self._dict(summary.get("bctc_3q")).get("periods")):
            items.append({"label": "Đọc BCTC gần nhất", "status": "pending", "note": "So sánh lợi nhuận, tài sản, vốn chủ và các chỉ tiêu sinh lời qua các kỳ."})
        if summary.get("weaknesses"):
            items.append({"label": "Kiểm tra rủi ro chính", "status": "pending", "note": self._string_list(summary.get("weaknesses"))[0]})
        return items

    def _sanitize_action_row(self, row: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(row)
        for key in ("action", "trigger", "condition", "price_zone", "price_zone_note", "position_size", "position_size_note", "stop_loss", "note", "risk_note", "source_basis"):
            sanitized[key] = self._sanitize_investment_language(sanitized.get(key))
        return sanitized

    def _sanitize_investment_language(self, value: Any) -> str:
        text = self._text(value, "")
        replacements = {
            r"\bmua ngay\b": "theo dõi và chờ xác nhận",
            r"\bbán ngay\b": "giảm rủi ro theo kế hoạch đã xác định",
            r"\bmua gấp\b": "theo dõi và chờ xác nhận",
            r"\bbán gấp\b": "giảm rủi ro theo kế hoạch đã xác định",
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _bank_metrics(self) -> list[tuple[str, str]]:
        return [
            ("Thu nhập lãi thuần", "net_interest_income"),
            ("Thu nhập phí thuần", "net_fee_income"),
            ("Thu nhập kinh doanh", "trading_income"),
            ("Thu nhập khác", "other_income"),
            ("Chi phí hoạt động", "operating_expenses"),
            ("Lợi nhuận trước thuế", "profit_before_tax"),
            ("Lợi nhuận sau thuế", "profit_after_tax"),
            ("Lợi nhuận cổ đông mẹ", "parent_profit"),
            ("Tổng tài sản", "total_assets"),
            ("Cho vay khách hàng", "customer_loans"),
            ("Tiền gửi khách hàng", "customer_deposits"),
            ("Vốn chủ sở hữu", "equity"),
            ("EPS", "eps"),
            ("BVPS", "bvps"),
            ("ROE", "roe"),
            ("ROA", "roa"),
            ("NIM", "nim"),
            ("Nợ xấu", "npl_ratio"),
            ("CASA", "casa_ratio"),
            ("CIR", "cir"),
        ]

    def _non_bank_metrics(self) -> list[tuple[str, str]]:
        return [
            ("Doanh thu", "revenue"),
            ("Lợi nhuận gộp", "gross_profit"),
            ("Lợi nhuận hoạt động", "operating_profit"),
            ("Lợi nhuận trước thuế", "profit_before_tax"),
            ("Lợi nhuận sau thuế", "profit_after_tax"),
            ("Tổng tài sản", "total_assets"),
            ("Nợ phải trả", "total_liabilities"),
            ("Vốn chủ sở hữu", "equity"),
            ("Tiền và tương đương tiền", "cash_and_equivalents"),
            ("Hàng tồn kho", "inventory"),
            ("Nợ vay ngắn hạn", "short_term_debt"),
            ("Nợ vay dài hạn", "long_term_debt"),
            ("Dòng tiền HĐKD", "operating_cash_flow"),
            ("Dòng tiền đầu tư", "investing_cash_flow"),
            ("Dòng tiền tài chính", "financing_cash_flow"),
            ("EPS", "eps"),
            ("BVPS", "bvps"),
            ("ROE", "roe"),
            ("ROA", "roa"),
            ("Biên lợi nhuận gộp", "gross_margin"),
            ("Biên lợi nhuận ròng", "net_margin"),
            ("Nợ/VCSH", "debt_to_equity"),
        ]

    def _valid_financial_value(self, period: dict[str, Any], key: str) -> Any:
        if key in {"total_assets", "equity", "customer_loans", "customer_deposits", "roa", "roe"}:
            period = self.stock_data_service.sanitize_financial_period(period)
        value = period.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            return value
        return None

    def _audit_row(
        self,
        field: str,
        raw_available: bool,
        normalized_available: bool,
        summary_available: bool,
        presentation_available: bool,
        final_presentation: Any,
    ) -> dict[str, Any]:
        cause = "ok" if presentation_available else "mapping_missing" if normalized_available else "source_missing"
        return {
            "field": field,
            "raw_available": bool(raw_available),
            "normalized_available": bool(normalized_available),
            "summary_available": bool(summary_available),
            "presentation_available": bool(presentation_available),
            "final_response_available": bool(final_presentation),
            "cause": cause,
        }

    def _card_available(self, section: dict[str, Any], label: str) -> bool:
        cards = section.get("cards") if isinstance(section.get("cards"), list) else []
        for card in cards:
            if isinstance(card, dict) and card.get("label") == label:
                return card.get("status") == AVAILABLE_STATUS and card.get("value") not in (None, "", MISSING_DISPLAY)
        return False

    def _missing_quick_fields(self, presentation: dict[str, Any]) -> list[str]:
        quick = self._dict(presentation.get("quick_overview"))
        missing = []
        if not self._card_available(quick, "Biến động kỳ chart"):
            missing.append("quick_overview.cards.chart_period_change")
        return missing

    def _missing_action_fields(self, presentation: dict[str, Any]) -> list[str]:
        missing = []
        if not self._list(self._dict(presentation.get("action_table")).get("rows")):
            missing.append("action_table.rows")
        if not self._list(self._dict(presentation.get("scenario_table")).get("rows")):
            missing.append("scenario_table.rows")
        if not self._list(self._dict(presentation.get("checklist")).get("items")):
            missing.append("checklist.items")
        return missing

    def _chart_missing_reason(self, momentum: dict[str, Any], points: int) -> str:
        reason = momentum.get("missing_reason")
        if reason:
            return str(reason)
        if points < 2:
            return "Chưa đủ 2 điểm giá hợp lệ"
        return MISSING_DISPLAY

    def _financial_source(self, summary: dict[str, Any]) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        source = self._text(bctc.get("source") or self._dict(summary.get("data_quality")).get("financial_source"), "Dữ liệu BCTC đã chuẩn hóa")
        return self._source_display(source)

    def _format_signed_percent(self, value: Any) -> str:
        numeric = self._number(value)
        if numeric is None:
            return MISSING_DISPLAY
        sign = "+" if numeric > 0 else ""
        formatted = f"{numeric:.2f}".replace(".", ",")
        return f"{sign}{formatted}%"

    def _format_plain_percent(self, value: Any) -> str:
        numeric = self._number(value)
        if numeric is None:
            return MISSING_DISPLAY
        formatted = f"{numeric:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{formatted}%"

    def _format_trading_value_billion(self, value: Any) -> str:
        numeric = self._number(value)
        if numeric is None:
            return MISSING_DISPLAY
        return f"{numeric:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".") + " tỷ đồng"

    def _parse_trading_value_from_text(self, value: Any) -> float | None:
        text = str(value or "")
        match = re.search(r"([0-9][0-9.,]*)\s*tỷ\s*đồng", text, flags=re.IGNORECASE)
        if not match:
            return None
        raw = match.group(1)
        if "," in raw and "." in raw:
            raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None

    def _source_backed_enrichment_policy(self) -> dict[str, Any]:
        return {
            "source_backed_research_enabled": bool(self.settings.enable_source_backed_research),
            "deep_research_crawl_enabled": bool(self.settings.enable_deep_research_crawl),
            "enabled": bool(self.settings.enable_source_backed_missing_field_enrichment),
            "allowed_sources": self.settings.missing_field_enrichment_allowed_source_list,
            "timeout_ms": self.settings.missing_field_enrichment_timeout_ms,
            "max_attempts": self.settings.missing_field_enrichment_max_attempts,
            "policy": self.settings.report_missing_value_policy,
            "numeric_facts_require_source": bool(self.settings.report_require_source_for_numeric_facts),
            "model_inference_for_qualitative_fields": bool(self.settings.report_allow_model_inference_for_qualitative_fields),
            "show_missing_reason": bool(self.settings.report_show_missing_reason),
            "safe_action_fallback": bool(self.settings.report_allow_safe_action_fallback),
            "safe_scenario_fallback": bool(self.settings.report_allow_safe_scenario_fallback),
            "safe_checklist_fallback": bool(self.settings.report_allow_safe_checklist_fallback),
        }

    def _source_display(self, value: Any) -> str:
        text = str(value or "").strip()
        mapping = {
            "vietstock": "Vietstock Finance BCTC",
            "vietstock finance": "Vietstock Finance BCTC",
            "vietstock finance bctt": "Vietstock Finance BCTC",
            "vietstock finance bctc": "Vietstock Finance BCTC",
            "cafef": "CafeF tài chính",
            "cafef bctc": "CafeF tài chính",
            "cafef tài chính": "CafeF tài chính",
            "cafef company overview": "CafeF thông tin doanh nghiệp",
            "cafef thông tin doanh nghiệp": "CafeF thông tin doanh nghiệp",
            "backend analysis-data": "Dữ liệu Backend",
        }
        return mapping.get(text.lower(), text or "Dữ liệu BCTC đã chuẩn hóa")

    def _status_label(self, status: Any) -> str:
        mapping = {
            "available": AVAILABLE_LABEL,
            "success": AVAILABLE_LABEL,
            "partial": "Ghi nhận một phần",
            "insufficient": "Chưa đủ dữ liệu",
            "failed": "Chưa lấy được",
            "missing": MISSING_LABEL,
            "disabled": "Chưa cấu hình",
            "skipped": "Bỏ qua",
        }
        return mapping.get(str(status or "").strip().lower(), MISSING_LABEL)

    def _checklist_label(self, text: str) -> str:
        lower = text.lower()
        if "bctc" in lower or "lợi nhuận" in lower or "tài chính" in lower:
            return "Đọc BCTC gần nhất"
        if "giá" in lower or "thanh khoản" in lower or "volume" in lower:
            return "Kiểm tra xu hướng giá"
        if "rủi ro" in lower or "risk" in lower:
            return "Kiểm tra rủi ro chính"
        if "tin" in lower or "nghiên cứu" in lower:
            return "Đối chiếu tin tức"
        return "Kiểm tra dữ liệu"

    def _summary_keys(self, summary: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
        return [key for key in keys if summary.get(key) not in (None, "", {}, [])]

    def _number(self, *values: Any) -> float | None:
        for value in values:
            if value in (None, "") or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                numeric = float(value)
                if math.isfinite(numeric):
                    return numeric
            try:
                numeric = float(str(value).replace(",", "").replace("%", "").strip())
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                return numeric
        return None

    def _int(self, *values: Any) -> int:
        numeric = self._number(*values)
        return int(numeric) if numeric is not None else 0

    def _value(self, value: Any) -> str:
        if value in (None, ""):
            return MISSING_DISPLAY
        if isinstance(value, float):
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    def _text(self, value: Any, default: str) -> str:
        if value in (None, "", MISSING_DISPLAY, "Chưa xác định"):
            return default
        text = str(value).strip()
        return default if text in {MISSING_DISPLAY, "Chưa xác định"} else text

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

    def _dedupe_rows(self, rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        result = []
        seen: set[tuple[str, ...]] = set()
        for row in rows:
            clean = {key: value for key, value in row.items() if value not in (None, "")}
            if not clean:
                continue
            signature = tuple(str(clean.get(key) or "").strip().lower() for key in keys)
            if signature in seen:
                continue
            seen.add(signature)
            result.append(clean)
        return result
