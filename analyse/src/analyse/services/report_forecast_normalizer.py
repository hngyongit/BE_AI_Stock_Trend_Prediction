from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from analyse.config.settings import Settings, get_settings


class ReportForecastNormalizer:
    """Guarantee qualitative forecast sections before a report is returned."""

    REQUIRED_SCENARIOS = ("Tích cực", "Cơ sở", "Thận trọng")
    BANNED_PHRASES = (
        "Chưa xác minh",
        "Chưa xác định",
        "Không có dữ liệu",
        "Không đủ dữ liệu",
        "N/A",
        "unknown",
        "null",
        "undefined",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def normalize_summary(self, summary: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        before = self._section_counts(summary)
        banned_found: list[str] = []
        normalized = deepcopy(summary)
        normalized["forecast_scenarios"] = self.ensure_scenarios(normalized, banned_found=banned_found)
        normalized["scenarios"] = normalized["forecast_scenarios"]
        normalized["scenario_table"] = {"rows": normalized["forecast_scenarios"]}
        normalized["scenario_matrix"] = [
            {
                "scenario": row.get("scenario"),
                "probability_pct": row.get("probability_pct"),
                "time_horizon": row.get("time_horizon"),
                "condition": row.get("condition"),
                "response": row.get("expected_behavior"),
                "supporting_signals": row.get("supporting_signals"),
                "invalidation_signals": row.get("invalidation_signals"),
                "risk": row.get("risk_note"),
                "risk_note": row.get("risk_note"),
            }
            for row in normalized["forecast_scenarios"]
        ]
        normalized["checklist"] = self.ensure_checklist(normalized, banned_found=banned_found)
        normalized["action_plan"] = self.ensure_action_plan(normalized, banned_found=banned_found)
        normalized["executive_forecast"] = self.ensure_executive_forecast(normalized, banned_found=banned_found)
        normalized["risk_map"] = self.ensure_risk_map(normalized, banned_found=banned_found)
        after = self._section_counts(normalized)
        debug = {
            "scenarios_before": before["scenarios"],
            "scenarios_after": after["scenarios"],
            "checklist_before": before["checklist"],
            "checklist_after": after["checklist"],
            "action_rows_before": before["action_rows"],
            "action_rows_after": after["action_rows"],
            "fallback_used": (
                before["scenarios"] < 3
                or before["checklist"] < 5
                or before["action_rows"] < 2
                or bool(banned_found)
            ),
            "banned_phrases_found": sorted(set(banned_found)),
        }
        normalized["mandatory_forecast_sections_validation"] = debug
        return normalized, debug

    def ensure_scenarios(self, summary: dict[str, Any], *, banned_found: list[str] | None = None) -> list[dict[str, Any]]:
        existing = self._scenario_candidates(summary)
        matched: dict[str, dict[str, Any]] = {}
        for row in existing:
            self._collect_banned_from_value(row, banned_found)
            name = self._scenario_name(row)
            if name and name not in matched:
                matched[name] = row

        fallback = self._fallback_scenarios(summary)
        result: list[dict[str, Any]] = []
        for fallback_row in fallback:
            name = str(fallback_row["scenario"])
            source = matched.get(name, {})
            merged = {**fallback_row, **source}
            merged["scenario"] = name
            merged["probability_pct"] = self._number(merged.get("probability_pct"), fallback_row["probability_pct"])
            merged["time_horizon"] = self._clean_text(merged.get("time_horizon"), fallback_row["time_horizon"], banned_found)
            merged["condition"] = self._clean_text(merged.get("condition") or merged.get("trigger"), fallback_row["condition"], banned_found)
            merged["expected_behavior"] = self._clean_text(
                merged.get("expected_behavior") or merged.get("expectedBehavior") or merged.get("response"),
                fallback_row["expected_behavior"],
                banned_found,
            )
            merged["supporting_signals"] = self._clean_string_list(
                merged.get("supporting_signals") or merged.get("supportingSignals"),
                fallback_row["supporting_signals"],
                banned_found,
                min_items=2,
            )
            merged["invalidation_signals"] = self._clean_string_list(
                merged.get("invalidation_signals") or merged.get("invalidationSignals"),
                fallback_row["invalidation_signals"],
                banned_found,
                min_items=3,
            )
            merged["risk_note"] = self._clean_text(
                merged.get("risk_note") or merged.get("riskNote") or merged.get("risk"),
                fallback_row["risk_note"],
                banned_found,
            )
            result.append(merged)
        self._normalize_probabilities(result)
        return result

    def ensure_checklist(self, summary: dict[str, Any], *, banned_found: list[str] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for raw in self._checklist_candidates(summary):
            item = self._checklist_item(raw, banned_found=banned_found)
            if item:
                items.append(item)
        items = self._dedupe_dicts(items, ("label", "note"))
        for fallback in self._fallback_checklist(summary):
            if len(items) >= 5:
                break
            if not any(item["label"] == fallback["label"] for item in items):
                items.append(fallback)
        return items[:8]

    def ensure_action_plan(self, summary: dict[str, Any], *, banned_found: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
        source = self._dict(summary.get("action_plan") or summary.get("actionPlan") or summary.get("monitoring_plan"))
        required = {
            "short_term": 2,
            "medium_term": 2,
            "watch_points": 3,
            "risk_management": 3,
        }
        result: dict[str, list[dict[str, Any]]] = {}
        for key, minimum in required.items():
            raw_values = self._action_group_values(source, key)
            rows = [self._action_item(value, key, banned_found=banned_found) for value in raw_values]
            rows = [row for row in rows if row]
            rows = self._dedupe_dicts(rows, ("action", "condition", "risk_note"))
            for fallback in self._fallback_action_items(summary, key):
                if len(rows) >= minimum:
                    break
                if not any(row["action"] == fallback["action"] for row in rows):
                    rows.append(fallback)
            result[key] = rows[: max(minimum, 4)]
        return result

    def ensure_executive_forecast(self, summary: dict[str, Any], *, banned_found: list[str] | None = None) -> dict[str, Any]:
        existing = self._dict(summary.get("executive_forecast") or summary.get("executiveForecast"))
        scenarios = self._list(summary.get("forecast_scenarios"))
        primary = max(scenarios, key=lambda row: self._number(row.get("probability_pct"), 0)) if scenarios else {}
        return {
            "label": self._clean_text(existing.get("label"), "Dự báo xác suất tham khảo", banned_found),
            "primary_scenario": self._clean_text(existing.get("primary_scenario"), primary.get("scenario") or "Cơ sở", banned_found),
            "primary_probability_pct": self._number(existing.get("primary_probability_pct"), primary.get("probability_pct")),
            "confidence": existing.get("confidence") if existing.get("confidence") not in ("", "null", "unknown") else None,
            "basis": self._clean_text(
                existing.get("basis"),
                "Suy luận từ xu hướng giá, thanh khoản, điểm tổng, rủi ro, bối cảnh thị trường, độ phủ BCTC, peer và evidence hiện có.",
                banned_found,
            ),
            "disclaimer": self._clean_text(
                existing.get("disclaimer"),
                "Đây là forecast xác suất tham khảo, không phải khuyến nghị mua/bán hoặc cam kết lợi nhuận.",
                banned_found,
            ),
        }

    def ensure_risk_map(self, summary: dict[str, Any], *, banned_found: list[str] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in self._list_any(summary.get("risk_map") or summary.get("riskMap")):
            if isinstance(raw, dict):
                risk = self._clean_text(raw.get("risk") or raw.get("label"), "", banned_found)
                if risk:
                    rows.append(
                        {
                            "risk": risk,
                            "monitoring_signal": self._clean_text(
                                raw.get("monitoring_signal") or raw.get("monitoringSignal"),
                                "Đối chiếu với giá, thanh khoản, BCTC và tin tức mới.",
                                banned_found,
                            ),
                            "source": self._clean_text(raw.get("source"), "summary/evidence", banned_found),
                        }
                    )
            elif isinstance(raw, str):
                text = self._clean_text(raw, "", banned_found)
                if text:
                    rows.append({"risk": text, "monitoring_signal": "Đối chiếu với dữ liệu mới.", "source": "summary/evidence"})
        if rows:
            return rows[:6]
        return [
            {
                "risk": "Tín hiệu giá suy yếu hoặc thanh khoản biến động bất thường.",
                "monitoring_signal": "Theo dõi chuỗi giá và khối lượng ở các phiên kế tiếp.",
                "source": "Dữ liệu giá và thanh khoản",
            },
            {
                "risk": "BCTC mới làm thay đổi chất lượng lợi nhuận hoặc sức khỏe tài chính.",
                "monitoring_signal": "So sánh kỳ mới với các kỳ đã ghi nhận.",
                "source": "BCTC đã chuẩn hóa",
            },
        ]

    def presentation_counts(self, summary: dict[str, Any]) -> dict[str, int]:
        presentation = self._dict(summary.get("report_presentation"))
        return {
            "scenarios": len(self._list(self._dict(presentation.get("scenario_table")).get("rows"))),
            "checklist": len(self._list(self._dict(presentation.get("checklist")).get("items"))),
            "action_rows": len(self._list(self._dict(presentation.get("action_table")).get("rows"))),
        }

    def _fallback_scenarios(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        probs = self._probabilities(summary)
        signals = self._supporting_signals(summary)
        invalidations = self._invalidation_signals(summary)
        horizon = self._time_horizon(summary)
        return [
            {
                "scenario": "Tích cực",
                "probability_pct": probs[0],
                "time_horizon": horizon,
                "condition": "Giá giữ được động lượng, thanh khoản cải thiện và bối cảnh thị trường không xuất hiện tín hiệu xấu mới.",
                "expected_behavior": "Tín hiệu tích cực có thể được củng cố nếu các điều kiện xác nhận tiếp tục xuất hiện.",
                "supporting_signals": signals[:4],
                "invalidation_signals": invalidations,
                "risk_note": "Đây là kịch bản xác suất tham khảo, không phải khuyến nghị mua/bán.",
            },
            {
                "scenario": "Cơ sở",
                "probability_pct": probs[1],
                "time_horizon": horizon,
                "condition": "Giá dao động quanh vùng hiện tại trong khi thanh khoản và dữ liệu cơ bản chưa tạo xác nhận vượt trội.",
                "expected_behavior": "Xu hướng cần thêm dữ liệu xác nhận trước khi nâng mức đánh giá.",
                "supporting_signals": signals[:4],
                "invalidation_signals": invalidations,
                "risk_note": "Kịch bản cơ sở là khung quan sát, không phải chỉ dẫn giao dịch cá nhân hóa.",
            },
            {
                "scenario": "Thận trọng",
                "probability_pct": probs[2],
                "time_horizon": horizon,
                "condition": "Giá suy yếu, thanh khoản biến động bất lợi hoặc tin tức/BCTC mới làm giảm độ tin cậy của luận điểm.",
                "expected_behavior": "Ưu tiên kiểm tra lại rủi ro và giảm mức tự tin của kịch bản tích cực.",
                "supporting_signals": self._risk_signals(summary),
                "invalidation_signals": [
                    "Tín hiệu tích cực chỉ được khôi phục khi giá, thanh khoản và dữ liệu mới cùng xác nhận trở lại.",
                    *invalidations[:2],
                ],
                "risk_note": "Kịch bản thận trọng nhấn mạnh quản trị rủi ro, không phải khuyến nghị bán.",
            },
        ]

    def _fallback_checklist(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        financial_source = self._financial_source(summary)
        return [
            {
                "label": "Kiểm tra xu hướng giá",
                "status": "pending",
                "note": "Đối chiếu biến động kỳ chart, thanh khoản và vùng giá hiện tại trước khi đánh giá tiếp.",
                "source_basis": "Dữ liệu giá và thanh khoản",
            },
            {
                "label": "Đối chiếu thanh khoản",
                "status": "pending",
                "note": "Quan sát xem khối lượng có xác nhận hướng biến động giá hay chỉ tạo nhiễu ngắn hạn.",
                "source_basis": "Dữ liệu giá và thanh khoản",
            },
            {
                "label": "Đọc BCTC gần nhất",
                "status": "pending",
                "note": "So sánh lợi nhuận, tài sản, vốn chủ và các chỉ tiêu sinh lời qua những kỳ đã ghi nhận.",
                "source_basis": financial_source,
            },
            {
                "label": "So sánh bối cảnh thị trường",
                "status": "pending",
                "note": "Đặt tín hiệu của mã trong bối cảnh VN-Index, thanh khoản thị trường và mức độ risk-on/risk-off.",
                "source_basis": "Bối cảnh thị trường",
            },
            {
                "label": "Theo dõi tín hiệu vô hiệu",
                "status": "pending",
                "note": "Kiểm tra giá suy yếu kèm thanh khoản cao, BCTC kém hơn kỳ trước hoặc tin tức tiêu cực đáng tin cậy.",
                "source_basis": "Kịch bản và bản đồ rủi ro",
            },
        ]

    def _fallback_action_items(self, summary: dict[str, Any], group: str) -> list[dict[str, Any]]:
        max_position = self._format_percent(getattr(self.settings, "default_max_position_pct", 12.0))
        risk_pct = self._format_percent(getattr(self.settings, "default_risk_per_trade_pct", 1.0))
        common_price_note = "Dùng vùng giá hiện tại làm mốc quan sát nếu chưa có vùng hỗ trợ/kháng cự đáng tin cậy từ dữ liệu kỹ thuật."
        templates = {
            "short_term": [
                (
                    "Theo dõi phản ứng giá và thanh khoản quanh vùng giá hiện tại.",
                    "Chỉ nâng mức đánh giá khi chuỗi giá và khối lượng cùng xác nhận rõ hơn.",
                    "Dữ liệu giá và thanh khoản",
                ),
                (
                    "Ghi nhận tín hiệu động lượng trong các phiên kế tiếp.",
                    "Ưu tiên kịch bản cơ sở nếu giá đi ngang và thanh khoản chưa cải thiện.",
                    "Momentum và thanh khoản",
                ),
            ],
            "medium_term": [
                (
                    "Đối chiếu BCTC mới với các kỳ đã ghi nhận.",
                    "Đánh giá lại triển vọng nếu lợi nhuận, biên lợi nhuận hoặc chất lượng tài sản thay đổi đáng kể.",
                    "BCTC đã chuẩn hóa",
                ),
                (
                    "So sánh tín hiệu của mã với peer và bối cảnh thị trường.",
                    "Theo dõi liệu điểm số/peer context ủng hộ hay làm suy yếu kịch bản cơ sở.",
                    "Peer và market context",
                ),
            ],
            "watch_points": [
                (
                    "Theo dõi biến động kỳ chart và thanh khoản.",
                    "Tín hiệu đáng chú ý hơn khi giá biến động cùng khối lượng xác nhận.",
                    "Dữ liệu giá và thanh khoản",
                ),
                (
                    "Theo dõi VN-Index và trạng thái thị trường chung.",
                    "Cẩn trọng hơn nếu thị trường chuyển sang trạng thái phòng thủ.",
                    "Bối cảnh thị trường",
                ),
                (
                    "Theo dõi tin tức doanh nghiệp/ngành mới.",
                    "Ưu tiên nguồn công bố hoặc nguồn tài chính uy tín trước khi thay đổi luận điểm.",
                    "Tin tức và evidence nguồn",
                ),
            ],
            "risk_management": [
                (
                    "Định nghĩa tín hiệu vô hiệu trước khi mô phỏng hành động.",
                    "Tín hiệu vô hiệu gồm giá suy yếu kèm thanh khoản cao hoặc dữ liệu mới làm luận điểm xấu đi.",
                    "Kịch bản thận trọng",
                ),
                (
                    "Giới hạn rủi ro trong khung mô phỏng danh mục.",
                    f"Dùng rủi ro tham chiếu {risk_pct} vốn và không vượt quá {max_position} danh mục giả định.",
                    "Thiết lập quản trị rủi ro",
                ),
                (
                    "Đánh giá lại mức tự tin khi dữ liệu nguồn thay đổi.",
                    "Hạ mức conviction nếu BCTC, thị trường chung hoặc tin tức mới đi ngược kịch bản cơ sở.",
                    "Data quality và risk map",
                ),
            ],
        }
        rows = []
        for action, condition, source_basis in templates[group]:
            rows.append(
                {
                    "action": action,
                    "condition": condition,
                    "price_zone": None,
                    "price_zone_note": common_price_note,
                    "position_size_note": f"Không vượt quá {max_position} danh mục giả định nếu chỉ dùng cho mô phỏng.",
                    "risk_note": "Không phải khuyến nghị mua/bán.",
                    "source_basis": source_basis,
                }
            )
        return rows

    def _scenario_candidates(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        sources = [
            self._dict(summary.get("scenario_table")).get("rows"),
            summary.get("forecast_scenarios"),
            summary.get("scenarios"),
            summary.get("scenario_matrix"),
            summary.get("scenarioMatrix"),
        ]
        for source in sources:
            if isinstance(source, list):
                result.extend([item for item in source if isinstance(item, dict)])
            elif isinstance(source, dict):
                if isinstance(source.get("rows"), list):
                    result.extend([item for item in source["rows"] if isinstance(item, dict)])
                else:
                    result.extend([item for item in source.values() if isinstance(item, dict)])
        return result

    def _checklist_candidates(self, summary: dict[str, Any]) -> list[Any]:
        result: list[Any] = []
        for source in (
            summary.get("checklist"),
            summary.get("watch_points"),
            summary.get("watchPoints"),
            summary.get("risk_management"),
            summary.get("riskManagement"),
            summary.get("signals"),
            summary.get("risks"),
            summary.get("weaknesses"),
        ):
            if isinstance(source, list):
                result.extend(source)
            elif source:
                result.append(source)
        return result

    def _action_group_values(self, source: dict[str, Any], key: str) -> list[Any]:
        alias_map = {
            "short_term": ("short_term", "shortTerm"),
            "medium_term": ("medium_term", "mediumTerm"),
            "watch_points": ("watch_points", "watchPoints"),
            "risk_management": ("risk_management", "riskManagement"),
        }
        values: list[Any] = []
        for alias in alias_map[key]:
            value = source.get(alias)
            if isinstance(value, list):
                values.extend(value)
            elif value not in (None, "", {}, []):
                values.append(value)
        return values

    def _checklist_item(self, value: Any, *, banned_found: list[str] | None) -> dict[str, Any] | None:
        if isinstance(value, dict):
            label = self._clean_text(value.get("label") or value.get("title") or value.get("item"), "", banned_found)
            note = self._clean_text(value.get("note") or value.get("description") or value.get("risk") or value.get("content"), "", banned_found)
            source_basis = self._clean_text(value.get("source_basis") or value.get("sourceBasis") or value.get("source"), "Dữ liệu hiện có", banned_found)
            status = self._clean_text(value.get("status"), "pending", banned_found)
        else:
            note = self._clean_text(value, "", banned_found)
            label = self._checklist_label(note) if note else ""
            source_basis = "Dữ liệu hiện có"
            status = "pending"
        if not label or not note:
            return None
        return {"label": label, "status": status or "pending", "note": note, "source_basis": source_basis}

    def _action_item(self, value: Any, group: str, *, banned_found: list[str] | None) -> dict[str, Any] | None:
        fallback = self._fallback_action_items({}, group)[0]
        if isinstance(value, dict):
            action = self._clean_text(value.get("action") or value.get("task") or value.get("note") or value.get("content"), fallback["action"], banned_found)
            condition = self._clean_text(value.get("condition") or value.get("trigger") or value.get("signal"), fallback["condition"], banned_found)
            price_zone = self._nullable_price_field(value.get("price_zone") or value.get("priceZone") or value.get("zone"), banned_found)
            price_note = self._clean_text(value.get("price_zone_note") or value.get("priceZoneNote"), fallback["price_zone_note"], banned_found)
            position_note = self._clean_text(value.get("position_size_note") or value.get("positionSizeNote") or value.get("position_size"), fallback["position_size_note"], banned_found)
            risk_note = self._clean_text(value.get("risk_note") or value.get("risk") or value.get("guardrail"), fallback["risk_note"], banned_found)
            source_basis = self._clean_text(value.get("source_basis") or value.get("sourceBasis") or value.get("source"), fallback["source_basis"], banned_found)
        elif value not in (None, "", [], {}):
            action = self._clean_text(value, fallback["action"], banned_found)
            condition = fallback["condition"]
            price_zone = None
            price_note = fallback["price_zone_note"]
            position_note = fallback["position_size_note"]
            risk_note = fallback["risk_note"]
            source_basis = fallback["source_basis"]
        else:
            return None
        return {
            "action": action,
            "condition": condition,
            "price_zone": price_zone,
            "price_zone_note": price_note,
            "position_size_note": position_note,
            "risk_note": risk_note,
            "source_basis": source_basis,
        }

    def _probabilities(self, summary: dict[str, Any]) -> list[int]:
        scores = self._dict(summary.get("scores"))
        momentum = self._dict(summary.get("momentum"))
        market = self._dict(summary.get("hose_market_context"))
        overall = self._number(scores.get("overall_score"), 50)
        risk = self._number(scores.get("risk_score"), 50)
        confidence = self._number(scores.get("score_confidence"), 0.5)
        if confidence is not None and confidence <= 1:
            confidence *= 100
        chart_change = self._number(momentum.get("chart_period_change_pct"), 0)
        market_score = self._number(market.get("market_health_score"), 50)
        positive = 30 + (overall - 50) * 0.22 + max(-7, min(7, chart_change * 0.35)) + (market_score - 50) * 0.1 - max(0, risk - 60) * 0.1
        cautious = 25 + max(0, risk - 50) * 0.25 + max(0, -chart_change) * 0.3 + max(0, 50 - market_score) * 0.15
        if confidence < 55:
            cautious += 6
            positive -= 4
        positive = max(15, min(45, positive))
        cautious = max(15, min(45, cautious))
        base = max(20, 100 - positive - cautious)
        total = positive + base + cautious
        values = [round(positive / total * 100), round(base / total * 100), round(cautious / total * 100)]
        values[1] += 100 - sum(values)
        return values

    def _supporting_signals(self, summary: dict[str, Any]) -> list[str]:
        signals: list[str] = []
        scores = self._dict(summary.get("scores"))
        momentum = self._dict(summary.get("momentum"))
        coverage = self._dict(summary.get("data_coverage"))
        market = self._dict(summary.get("hose_market_context"))
        peer_count = len(self._list(self._dict(summary.get("industry_peer_context")).get("peers")))
        news_count = len(self._list(self._dict(summary.get("external_research_context")).get("items")))
        if scores.get("overall_score") is not None:
            signals.append(f"Điểm tổng {scores.get('overall_score')}/100 được dùng làm tín hiệu định lượng nền.")
        if scores.get("risk_label") or scores.get("risk_score") is not None:
            signals.append(f"Mức rủi ro hiện được ghi nhận là {scores.get('risk_label') or scores.get('risk_score')}.")
        if momentum.get("chart_period_change_pct") is not None:
            signals.append(f"Biến động kỳ chart {momentum.get('chart_period_change_pct')}% là cơ sở đọc động lượng.")
        if market.get("status") or market.get("market_health_score") is not None:
            signals.append(f"Bối cảnh thị trường: {market.get('status') or str(market.get('market_health_score')) + '/100'}.")
        if coverage.get("financial_periods_count"):
            signals.append(f"Có {coverage.get('financial_periods_count')} kỳ BCTC dùng để đối chiếu xu hướng cơ bản.")
        if peer_count:
            signals.append(f"Có {peer_count} peer/ngữ cảnh ngành để so sánh tương đối.")
        if news_count:
            signals.append(f"Có {news_count} tin tức/nghiên cứu bên ngoài làm bối cảnh định tính.")
        return signals or ["Dữ liệu hiện có cho phép dựng khung quan sát xác suất với mức thận trọng phù hợp."]

    def _risk_signals(self, summary: dict[str, Any]) -> list[str]:
        risks = [self._clean_text(item, "", None) for item in self._list_any(summary.get("weaknesses"))]
        risks = [item for item in risks if item]
        if risks:
            return risks[:4]
        scores = self._dict(summary.get("scores"))
        if scores.get("risk_label") or scores.get("risk_score") is not None:
            return [f"Điểm rủi ro/mức rủi ro cần được kiểm tra lại khi dữ liệu mới xuất hiện: {scores.get('risk_label') or scores.get('risk_score')}."]
        return ["Rủi ro chính nằm ở việc tín hiệu giá, thanh khoản hoặc dữ liệu mới làm thay đổi luận điểm hiện tại."]

    def _invalidation_signals(self, summary: dict[str, Any]) -> list[str]:
        return [
            "Giá suy yếu kèm thanh khoản tăng bất thường.",
            "BCTC mới cho thấy lợi nhuận, biên lợi nhuận hoặc chất lượng tài sản suy giảm.",
            "Thị trường chung chuyển sang trạng thái thận trọng hoặc xuất hiện tin tức tiêu cực đáng tin cậy.",
        ]

    def _section_counts(self, summary: dict[str, Any]) -> dict[str, int]:
        action = self._dict(summary.get("action_plan") or summary.get("actionPlan"))
        action_rows = sum(len(self._action_group_values(action, key)) for key in ("short_term", "medium_term", "watch_points", "risk_management"))
        scenario_candidates = self._scenario_candidates(summary)
        scenario_names = {name for row in scenario_candidates if (name := self._scenario_name(row))}
        return {
            "scenarios": len(scenario_names) if scenario_names else len(scenario_candidates),
            "checklist": len(self._checklist_candidates(summary)),
            "action_rows": action_rows,
        }

    def _scenario_name(self, row: dict[str, Any]) -> str | None:
        text = str(row.get("scenario") or row.get("name") or row.get("label") or "").strip().lower()
        if "tích cực" in text or "positive" in text or "bull" in text:
            return "Tích cực"
        if "cơ sở" in text or "base" in text or "trung tính" in text:
            return "Cơ sở"
        if "thận trọng" in text or "cautious" in text or "bear" in text or "tiêu cực" in text:
            return "Thận trọng"
        return None

    def _clean_text(self, value: Any, fallback: str, banned_found: list[str] | None) -> str:
        text = str(value).strip() if value not in (None, "") else ""
        if not text or self._contains_banned(text, banned_found):
            return fallback
        return self._sanitize_investment_language(text)

    def _clean_string_list(self, value: Any, fallback: list[str], banned_found: list[str] | None, *, min_items: int = 1) -> list[str]:
        items: list[str] = []
        if isinstance(value, list):
            for item in value:
                text = self._clean_text(item, "", banned_found)
                if text:
                    items.append(text)
        elif isinstance(value, str):
            text = self._clean_text(value, "", banned_found)
            if text:
                items.append(text)
        for item in fallback:
            if len(items) >= min_items:
                break
            if item not in items:
                items.append(item)
        return items or fallback[:min_items]

    def _contains_banned(self, text: str, banned_found: list[str] | None) -> bool:
        normalized = self._normalize_text(text)
        for phrase in self.BANNED_PHRASES:
            phrase_key = self._normalize_text(phrase)
            if phrase_key and phrase_key in normalized:
                if banned_found is not None:
                    banned_found.append(phrase)
                return True
        return False

    def _collect_banned_from_value(self, value: Any, banned_found: list[str] | None) -> None:
        if banned_found is None:
            return
        if isinstance(value, dict):
            for item in value.values():
                self._collect_banned_from_value(item, banned_found)
            return
        if isinstance(value, list):
            for item in value:
                self._collect_banned_from_value(item, banned_found)
            return
        if isinstance(value, str):
            self._contains_banned(value, banned_found)

    def _nullable_price_field(self, value: Any, banned_found: list[str] | None) -> Any:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if self._contains_banned(text, banned_found):
            return None
        return value

    def _normalize_probabilities(self, rows: list[dict[str, Any]]) -> None:
        values = [self._number(row.get("probability_pct"), None) for row in rows]
        if any(value is None for value in values):
            fallback = [30, 45, 25]
            for row, prob in zip(rows, fallback, strict=False):
                row["probability_pct"] = prob
            return
        total = sum(float(value) for value in values if value is not None)
        if not total or not math.isfinite(total):
            fallback = [30, 45, 25]
            for row, prob in zip(rows, fallback, strict=False):
                row["probability_pct"] = prob
            return
        normalized = [round(float(value) / total * 100) for value in values if value is not None]
        normalized[1] += 100 - sum(normalized)
        for row, prob in zip(rows, normalized, strict=False):
            row["probability_pct"] = int(max(0, min(100, prob)))

    def _action_group_total(self, plan: dict[str, Any]) -> int:
        return sum(len(self._list_any(plan.get(key))) for key in ("short_term", "medium_term", "watch_points", "risk_management"))

    def _financial_source(self, summary: dict[str, Any]) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        return str(bctc.get("source") or self._dict(summary.get("data_quality")).get("financial_source") or "BCTC đã chuẩn hóa")

    def _time_horizon(self, summary: dict[str, Any]) -> str:
        plan = self._dict(summary.get("investment_plan"))
        horizon = str(plan.get("time_horizon") or "").strip()
        mapping = {
            "short": "1-4 tuần",
            "short_term": "1-4 tuần",
            "medium": "1-3 tháng",
            "medium_term": "1-3 tháng",
            "long": "3-6 tháng",
            "long_term": "3-6 tháng",
        }
        return mapping.get(horizon, "1-3 tháng")

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

    def _sanitize_investment_language(self, value: str) -> str:
        replacements = {
            r"\bmua ngay\b": "theo dõi và chờ xác nhận",
            r"\bbán ngay\b": "giảm rủi ro theo kế hoạch đã xác định",
            r"\bmua gấp\b": "theo dõi và chờ xác nhận",
            r"\bbán gấp\b": "giảm rủi ro theo kế hoạch đã xác định",
        }
        text = value
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _dedupe_dicts(self, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for row in rows:
            key = tuple(str(row.get(field) or "").strip().lower() for field in fields)
            if key in seen:
                continue
            result.append(row)
            seen.add(key)
        return result

    def _number(self, value: Any, default: float | int | None) -> float | int | None:
        if value in (None, "") or isinstance(value, bool):
            return default
        try:
            numeric = float(str(value).replace("%", "").replace(",", ".").strip())
        except (TypeError, ValueError):
            return default
        return numeric if math.isfinite(numeric) else default

    def _format_percent(self, value: Any) -> str:
        numeric = self._number(value, None)
        if numeric is None:
            return "mức đã cấu hình"
        return f"{numeric:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"

    def _normalize_text(self, value: str) -> str:
        text = str(value or "").strip().lower()
        text = text.replace("–", "-").replace("—", "-")
        return re.sub(r"\s+", " ", text)

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def _list_any(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []
