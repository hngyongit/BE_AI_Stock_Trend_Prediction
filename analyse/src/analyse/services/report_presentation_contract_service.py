from __future__ import annotations

from copy import deepcopy
from typing import Any

from analyse.schemas.report_presentation import ReportPresentation


AVAILABLE_STATUS = "available"
AVAILABLE_LABEL = "Đã ghi nhận"
MISSING_STATUS = "missing"
MISSING_LABEL = "Chưa xác minh"
UNVERIFIED_VALUES = {None, "", "Chưa xác minh", "Chưa xác định", "Không có dữ liệu", "Không đủ dữ liệu", "N/A", "unknown", "null", "undefined"}


class ReportPresentationContractService:
    """Validate and repair the internal report_presentation dict without changing public keys."""

    LIST_SECTIONS = {
        "quick_overview": ("cards", "Tổng quan nhanh"),
        "market_context_view": ("cards", "Bối cảnh thị trường"),
        "financial_table": ("rows", "Bảng tài chính 3 quý"),
        "action_table": ("rows", "Kế hoạch hành động"),
        "scenario_table": ("rows", "Kịch bản"),
        "checklist": ("items", "Checklist"),
        "data_coverage": ("items", "Độ phủ dữ liệu"),
    }
    MINIMUM_ITEMS = {
        "scenario_table": 3,
        "checklist": 5,
        "action_table": 2,
    }

    def normalize_and_validate(self, payload: dict[str, Any] | None, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        working = deepcopy(payload) if isinstance(payload, dict) else {}
        warnings = self.validate_invariants(working)
        repaired = self.repair_presentation(working, warnings, summary=summary)

        model = ReportPresentation.model_validate(repaired)
        normalized = model.model_dump(mode="json")

        post_warnings = self.validate_invariants(normalized)
        if post_warnings:
            normalized = self.repair_presentation(normalized, post_warnings, summary=summary)
            normalized = ReportPresentation.model_validate(normalized).model_dump(mode="json")

        all_warnings = self._dedupe_warnings([*warnings, *post_warnings])
        if all_warnings:
            normalized["contract_warnings"] = self._merge_warning_rows(normalized.get("contract_warnings"), all_warnings)
        self._sync_coverage_rows(normalized)
        return normalized

    def validate_invariants(self, presentation: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(presentation, dict):
            return [self._warning("", "root_invalid_type", "report_presentation must be a dict")]

        warnings: list[dict[str, Any]] = []
        for section, (list_key, _) in self.LIST_SECTIONS.items():
            value = presentation.get(section)
            if not isinstance(value, dict):
                warnings.append(self._warning(section, "section_invalid_type", f"{section} must be a dict"))
                continue
            rows = value.get(list_key)
            if not isinstance(rows, list):
                warnings.append(self._warning(f"{section}.{list_key}", "list_invalid_type", f"{section}.{list_key} must be a list"))
                continue
            minimum = self.MINIMUM_ITEMS.get(section)
            if minimum and len(rows) < minimum:
                warnings.append(self._warning(f"{section}.{list_key}", "list_too_short", f"{section}.{list_key} must contain at least {minimum} items"))

        coverage = presentation.get("data_coverage")
        if isinstance(coverage, dict) and isinstance(coverage.get("items"), list):
            for index, item in enumerate(coverage["items"]):
                if isinstance(item, dict) and item.get("status") == AVAILABLE_STATUS and self._is_unverified_value(item.get("value")):
                    warnings.append(
                        self._warning(
                            f"data_coverage.items[{index}].value",
                            "available_unverified_value",
                            "data_coverage item cannot be available while value is unverified",
                        )
                    )
        return warnings

    def repair_presentation(
        self,
        presentation: dict[str, Any],
        warnings: list[dict[str, Any]] | None = None,
        *,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        repaired = deepcopy(presentation) if isinstance(presentation, dict) else {}
        for section, (list_key, title) in self.LIST_SECTIONS.items():
            section_payload = repaired.get(section)
            if not isinstance(section_payload, dict):
                section_payload = {"title": title, list_key: self._list_from_value(section_payload)}
            else:
                section_payload = dict(section_payload)
                section_payload.setdefault("title", title)
                section_payload[list_key] = self._list_from_value(section_payload.get(list_key))
            repaired[section] = section_payload

        self._repair_card_rows(repaired["quick_overview"], "cards")
        self._repair_card_rows(repaired["market_context_view"], "cards")
        self._repair_coverage(repaired)
        self._ensure_minimum_rows(repaired, "scenario_table", "rows", self._fallback_scenario_rows(summary or {}))
        self._ensure_minimum_rows(repaired, "checklist", "items", self._fallback_checklist_items(summary or {}))
        self._ensure_minimum_rows(repaired, "action_table", "rows", self._fallback_action_rows(summary or {}))
        self._sync_coverage_rows(repaired)
        return repaired

    def _ensure_minimum_rows(self, presentation: dict[str, Any], section: str, list_key: str, fallback_rows: list[dict[str, Any]]) -> None:
        payload = presentation[section]
        rows = self._list_from_value(payload.get(list_key))
        for fallback in fallback_rows:
            if len(rows) >= self.MINIMUM_ITEMS[section]:
                break
            if not self._contains_equivalent_row(rows, fallback):
                rows.append(fallback)
        payload[list_key] = rows
        if rows:
            payload["status"] = AVAILABLE_STATUS
            payload["status_label"] = AVAILABLE_LABEL
            payload["missing_reason"] = ""
        else:
            payload["status"] = MISSING_STATUS
            payload["status_label"] = MISSING_LABEL

    def _repair_card_rows(self, section: dict[str, Any], list_key: str) -> None:
        repaired_rows: list[dict[str, Any]] = []
        for item in self._list_from_value(section.get(list_key)):
            if isinstance(item, dict):
                repaired_rows.append(dict(item))
            elif item not in (None, ""):
                repaired_rows.append({"label": str(item), "value": str(item), "status": AVAILABLE_STATUS, "status_label": AVAILABLE_LABEL})
        section[list_key] = repaired_rows

    def _repair_coverage(self, presentation: dict[str, Any]) -> None:
        coverage = presentation["data_coverage"]
        repaired_items: list[dict[str, Any]] = []
        for item in self._list_from_value(coverage.get("items")):
            if isinstance(item, dict):
                row = dict(item)
            elif item in (None, ""):
                continue
            else:
                row = {"title": str(item), "label": str(item), "status": MISSING_STATUS, "status_label": MISSING_LABEL, "value": MISSING_LABEL}
            if row.get("status") == AVAILABLE_STATUS and self._is_unverified_value(row.get("value")):
                row["status"] = MISSING_STATUS
                row["status_label"] = MISSING_LABEL
                row["value"] = MISSING_LABEL
            if not row.get("title") and row.get("label"):
                row["title"] = row["label"]
            if not row.get("label") and row.get("title"):
                row["label"] = row["title"]
            repaired_items.append(row)
        coverage["items"] = repaired_items

    def _sync_coverage_rows(self, presentation: dict[str, Any]) -> None:
        coverage = presentation.get("data_coverage")
        if isinstance(coverage, dict) and isinstance(coverage.get("items"), list):
            presentation["coverage_rows"] = coverage["items"]

    def _fallback_scenario_rows(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        source_basis = self._source_basis(summary, "scenario")
        return [
            {
                "scenario": "Tích cực",
                "probability_pct": None,
                "time_horizon": "1-3 tháng",
                "condition": "Giá, thanh khoản và bối cảnh thị trường tiếp tục xác nhận theo hướng thuận lợi.",
                "expected_behavior": "Duy trì theo dõi với mức tự tin cao hơn nếu dữ liệu mới xác nhận cùng chiều.",
                "supporting_signals": ["Dựa trên điểm số, động lượng hoặc dữ liệu nguồn hiện có."],
                "invalidation_signals": ["Dữ liệu mới làm suy yếu xu hướng hoặc chất lượng cơ bản."],
                "risk": "Kịch bản chỉ là khung quan sát, không phải khuyến nghị giao dịch cá nhân hóa.",
                "risk_note": "Kịch bản chỉ là khung quan sát, không phải khuyến nghị giao dịch cá nhân hóa.",
                "source_basis": source_basis,
            },
            {
                "scenario": "Cơ sở",
                "probability_pct": None,
                "time_horizon": "1-3 tháng",
                "condition": "Dữ liệu hiện tại chưa tạo xác nhận vượt trội và cần tiếp tục đối chiếu nguồn.",
                "expected_behavior": "Ưu tiên kiểm chứng thêm trước khi nâng hoặc hạ mức đánh giá.",
                "supporting_signals": ["Dựa trên bộ dữ liệu đã chuẩn hóa trong báo cáo."],
                "invalidation_signals": ["Thị trường chung hoặc BCTC mới thay đổi đáng kể."],
                "risk": "Thiếu dữ liệu xác nhận có thể làm tín hiệu nhiễu.",
                "risk_note": "Thiếu dữ liệu xác nhận có thể làm tín hiệu nhiễu.",
                "source_basis": source_basis,
            },
            {
                "scenario": "Thận trọng",
                "probability_pct": None,
                "time_horizon": "1-3 tháng",
                "condition": "Giá, thanh khoản, BCTC hoặc tin tức mới chuyển sang bất lợi.",
                "expected_behavior": "Giảm mức tự tin của luận điểm và kiểm tra lại các rủi ro trọng yếu.",
                "supporting_signals": ["Dựa trên rủi ro và giới hạn dữ liệu đã ghi nhận."],
                "invalidation_signals": ["Tín hiệu tích cực chỉ được phục hồi khi dữ liệu mới xác nhận trở lại."],
                "risk": "Ưu tiên quản trị rủi ro khi độ phủ dữ liệu chưa đủ chắc.",
                "risk_note": "Ưu tiên quản trị rủi ro khi độ phủ dữ liệu chưa đủ chắc.",
                "source_basis": source_basis,
            },
        ]

    def _fallback_checklist_items(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        financial_source = self._source_basis(summary, "financial")
        return [
            {"label": "Kiểm tra xu hướng giá", "status": "pending", "note": "Đối chiếu biến động kỳ chart với thanh khoản và vùng giá hiện tại.", "source_basis": "Dữ liệu giá và thanh khoản"},
            {"label": "Đối chiếu thanh khoản", "status": "pending", "note": "Xác nhận khối lượng có ủng hộ hướng biến động giá hay không.", "source_basis": "Dữ liệu giá và thanh khoản"},
            {"label": "Đọc BCTC gần nhất", "status": "pending", "note": "So sánh các chỉ tiêu tài chính qua những kỳ đã ghi nhận.", "source_basis": financial_source},
            {"label": "So sánh bối cảnh thị trường", "status": "pending", "note": "Đặt tín hiệu của mã trong bối cảnh VN-Index và nhóm ngành.", "source_basis": "Bối cảnh thị trường"},
            {"label": "Theo dõi tín hiệu vô hiệu", "status": "pending", "note": "Kiểm tra tin tức, BCTC hoặc biến động giá làm suy yếu luận điểm.", "source_basis": "Kịch bản và bản đồ rủi ro"},
        ]

    def _fallback_action_rows(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        source_basis = self._source_basis(summary, "action")
        return [
            {
                "timeframe": "Ngắn hạn",
                "action": "Theo dõi phản ứng giá và thanh khoản quanh vùng hiện tại.",
                "condition": "Chỉ nâng mức đánh giá khi chuỗi giá và khối lượng cùng xác nhận rõ hơn.",
                "trigger": "Chỉ nâng mức đánh giá khi chuỗi giá và khối lượng cùng xác nhận rõ hơn.",
                "price_zone": "Dùng vùng giá hiện tại làm mốc quan sát nếu chưa có hỗ trợ/kháng cự đáng tin cậy.",
                "position_size": "Giữ tỷ trọng mô phỏng ở mức thận trọng cho tới khi dữ liệu xác nhận rõ hơn.",
                "stop_loss": "Xác định trước ngưỡng rủi ro hoặc vùng vô hiệu luận điểm trước khi hành động.",
                "note": "Chỉ dùng làm khung theo dõi, không phải khuyến nghị mua/bán.",
                "risk_note": "Không tăng rủi ro khi dữ liệu chưa xác nhận.",
                "source_basis": source_basis,
            },
            {
                "timeframe": "Trung hạn",
                "action": "Đối chiếu BCTC, peer và tin tức mới trước khi cập nhật luận điểm.",
                "condition": "Có dữ liệu công bố mới hoặc thay đổi đáng kể trong rủi ro/động lượng.",
                "trigger": "Có dữ liệu công bố mới hoặc thay đổi đáng kể trong rủi ro/động lượng.",
                "price_zone": "Chờ dữ liệu giá mới xác nhận vùng quan sát đáng tin cậy.",
                "position_size": "Ưu tiên bảo toàn vốn mô phỏng khi độ phủ dữ liệu còn hạn chế.",
                "stop_loss": "Giảm mức tự tin nếu dữ liệu nguồn làm luận điểm suy yếu.",
                "note": "Ưu tiên kiểm chứng dữ liệu gốc trước khi thay đổi kế hoạch theo dõi.",
                "risk_note": "Ưu tiên dữ liệu đã xác thực thay vì suy diễn thêm.",
                "source_basis": source_basis,
            },
        ]

    def _source_basis(self, summary: dict[str, Any], group: str) -> str:
        coverage = summary.get("data_coverage") if isinstance(summary.get("data_coverage"), dict) else {}
        if group == "financial":
            bctc = summary.get("bctc_3q") if isinstance(summary.get("bctc_3q"), dict) else {}
            return str(bctc.get("source") or coverage.get("financial_source") or "BCTC đã chuẩn hóa")
        if group == "action":
            return "Dữ liệu giá, BCTC và rủi ro đã chuẩn hóa"
        return "Tóm tắt và evidence hiện có"

    def _contains_equivalent_row(self, rows: list[Any], fallback: dict[str, Any]) -> bool:
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("scenario", "label", "action"):
                if row.get(key) and row.get(key) == fallback.get(key):
                    return True
        return False

    def _list_from_value(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return list(value)
        if value in (None, "", {}):
            return []
        if isinstance(value, dict):
            return [dict(value)]
        return [value]

    def _is_unverified_value(self, value: Any) -> bool:
        if value in UNVERIFIED_VALUES:
            return True
        if isinstance(value, str) and value.strip() in UNVERIFIED_VALUES:
            return True
        return False

    def _warning(self, field: str, code: str, message: str) -> dict[str, Any]:
        return {"field": field, "code": code, "message": message}

    def _dedupe_warnings(self, warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        result: list[dict[str, Any]] = []
        for warning in warnings:
            key = (str(warning.get("field", "")), str(warning.get("code", "")))
            if key in seen:
                continue
            seen.add(key)
            result.append(warning)
        return result

    def _merge_warning_rows(self, existing: Any, warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = [row for row in self._list_from_value(existing) if isinstance(row, dict)]
        rows.extend(warnings)
        return self._dedupe_warnings(rows)
