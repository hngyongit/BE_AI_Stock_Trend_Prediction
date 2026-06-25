from __future__ import annotations

import html
import re
from typing import Any

from analyse.schemas.common import DEFAULT_DISCLAIMER
from analyse.services.presentation_contract import normalize_percent_score
from analyse.services.presentation_contract import to_user_facing_source_name
from analyse.services.stock_data_service import StockDataService
from analyse.utils.datetime_utils import format_datetime_vi
from analyse.utils.datetime_utils import format_percent_ratio


class MarkdownService:
    """Tạo báo cáo Markdown tiếng Việt từ dữ liệu đã chuẩn hóa."""

    def build(self, summary: dict[str, Any], llm_narrative: str | None = None) -> str:
        symbol = self._text(summary.get("symbol"), "UNKNOWN")
        exchange = self._text(summary.get("scope_exchange"), "HOSE")
        company = self._text(summary.get("company"), "Chưa rõ tên công ty")
        decision = self._dict(summary.get("system_decision"))
        presentation = self._presentation(summary)
        executive = self._dict(presentation.get("executive_summary"))
        disclaimer = self._text(summary.get("disclaimer"), DEFAULT_DISCLAIMER)

        lines: list[str] = [
            f"# Báo cáo phân tích cổ phiếu {symbol} / {exchange}",
            "",
            f"**Doanh nghiệp:** {company}",
            f"**Trạng thái:** {self._text(executive.get('status') or decision.get('status'), 'CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN')}",
            f"**Điểm tổng:** {self._value(self._dict(summary.get('scores')).get('overall_score'))} | **Tỷ lệ tin cậy dữ liệu:** {self._format_confidence(self._dict(summary.get('scores')).get('score_confidence'))}",
            "",
            disclaimer,
            "",
            "## 1. Tóm tắt điều hành",
            "",
            self._executive_summary_block(presentation, summary),
            "",
            "## 2. Tổng quan doanh nghiệp",
            "",
            self._business_and_thesis_block(presentation, llm_narrative),
            "",
            "## 3. Bối cảnh thị trường",
            "",
            self._market_context_section(summary, presentation),
            "",
            "## 4. Diễn biến giá và thanh khoản",
            "",
            self._price_momentum_section(summary, presentation),
            "",
            "## 5. Phân tích tài chính",
            "",
            self._financial_analysis_section(summary, presentation),
            "",
            "## 6. Định giá",
            "",
            self._valuation_section(summary, presentation),
            "",
            "## 7. So sánh cùng ngành",
            "",
            self._peer_comparison_section(summary, presentation),
            "",
            "## 8. Mã tham khảo cùng nhóm/ngành",
            "",
            self._reference_candidates_section(summary, presentation),
            "",
            "## 9. Tin tức và dữ liệu bên ngoài",
            "",
            self._research_insights_section(summary, presentation),
            "",
            "## 10. Chấm điểm định lượng",
            "",
            self._professional_score_section(summary, presentation),
            "",
            "## 11. Lộ trình theo dõi",
            "",
            self._roadmap_section(presentation),
            "",
            "## 12. Rủi ro chính",
            "",
            self._risk_section(summary, presentation),
            "",
            "## 13. Độ phủ dữ liệu và giới hạn",
            "",
            self._data_quality_main_section(summary, presentation),
            "",
            "## 14. Phụ lục kỹ thuật và nguồn dữ liệu",
            "",
            self._appendix_section(summary),
        ]
        return self._sanitize_main_sections("\n".join(lines).strip() + "\n")

    def _presentation(self, summary: dict[str, Any]) -> dict[str, Any]:
        existing = self._dict(summary.get("report_presentation"))
        if existing:
            return existing
        scores = self._dict(summary.get("scores"))
        return {
            "executive_summary": {
                "status": self._dict(summary.get("system_decision")).get("status"),
                "main_thesis": self._dict(summary.get("system_decision")).get("action"),
                "key_positives": self._string_list(summary.get("strengths")),
                "key_risks": self._string_list(summary.get("weaknesses")),
                "confidence": scores.get("score_confidence"),
                "confidence_label": "Chưa xác minh",
                "checks_before_action": ["Đối chiếu dữ liệu gốc trước khi ra quyết định."],
            },
            "business_overview": {"description": "Chưa đủ dữ liệu xác thực để mô tả chi tiết mô hình kinh doanh.", "drivers": []},
            "market_context": "Bối cảnh thị trường cần được đối chiếu thêm.",
            "price_momentum": "Chuỗi giá cần được đối chiếu thêm.",
            "financial_analysis": "Bộ dữ liệu BCTC hiện chưa đủ để phân tích sâu.",
            "valuation": "Chưa đủ dữ liệu định giá xác thực.",
            "peer_note": "Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận.",
            "reference_candidates": [],
            "research_insights": {},
            "score_cards": self._fallback_score_cards(scores),
            "roadmap": [],
            "data_quality": {"user_notes": self._string_list(summary.get("data_quality_notes")), "technical_notes": self._string_list(summary.get("technical_data_quality_notes"))},
            "missing_display": "Chưa đủ dữ liệu xác thực",
        }

    def finalize_content(self, content: str | None, summary: dict[str, Any]) -> str | None:
        if not content or not content.strip():
            return None
        disclaimer = self._text(summary.get("disclaimer"), DEFAULT_DISCLAIMER)
        narrative = content.strip()
        narrative = narrative.replace(disclaimer, "").strip()
        return html.escape(narrative, quote=False) if narrative else None

    def _executive_summary_block(self, presentation: dict[str, Any], summary: dict[str, Any]) -> str:
        executive = self._dict(presentation.get("executive_summary"))
        rows = [
            ("Trạng thái", self._text(executive.get("status"), "CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN")),
            ("Luận điểm chính", self._text(executive.get("main_thesis"), "Chưa đủ dữ liệu xác thực để hình thành luận điểm đáng tin cậy.")),
            ("Tỷ lệ tin cậy", f"{self._format_confidence(executive.get('confidence'))} ({self._text(executive.get('confidence_label'), 'Chưa xác minh')})"),
            ("Điều cần kiểm tra trước hành động", "; ".join(self._string_list(executive.get("checks_before_action"))) or "Cần kiểm tra thêm"),
        ]
        return "\n\n".join(
            [
                self._simple_table(["Nội dung", "Nhận định"], rows),
                "**Điểm tích cực chính**",
                self._list_block(None, executive.get("key_positives")),
                "**Rủi ro/cần theo dõi**",
                self._list_block(None, executive.get("key_risks")),
            ]
        )

    def _business_and_thesis_block(self, presentation: dict[str, Any], llm_narrative: str | None) -> str:
        overview = self._dict(presentation.get("business_overview"))
        industry = self._dict(overview.get("industry"))
        source = self._overview_source_value(overview, industry)
        group = industry.get("industry_level_2") or industry.get("industry_group") or industry.get("group")
        detail = industry.get("industry_level_3") or industry.get("industry") or industry.get("industry_name")
        rows = [
            ("Doanh nghiệp", overview.get("company_name")),
            ("Sàn", overview.get("exchange")),
            ("Nhóm ngành", group),
            ("Mô tả ngắn", overview.get("business_overview")),
            ("Nguồn", source),
        ]
        lines = [
            self._text(overview.get("description"), "Chưa đủ dữ liệu xác thực để mô tả mô hình kinh doanh."),
            "",
            self._simple_table(["Nội dung", "Giá trị"], rows),
            "",
            "**Ban lãnh đạo**",
            self._leadership_markdown(overview.get("leadership")),
            "",
            "**Sở hữu / cổ đông lớn**",
            self._ownership_markdown(overview.get("ownership")),
            "",
            "**Nhóm ngành tham chiếu**",
            self._simple_table(["Nội dung", "Giá trị"], [("Nhóm ngành", group), ("Ngành chi tiết", detail), ("Nguồn", source)]),
            "",
            "**Bối cảnh cần theo dõi**",
            self._list_block(None, overview.get("drivers")),
        ]
        source_note = overview.get("source_note")
        if source_note:
            lines.extend(["", f"**Ghi chú nguồn:** {self._text(source_note, '')}"])
        if llm_narrative:
            lines.extend(["", "**Diễn giải bổ sung từ LLM đã kiểm soát**", "", llm_narrative])
        return "\n".join(lines)

    def _leadership_markdown(self, rows: Any) -> str:
        if not isinstance(rows, list) or not rows:
            return "Chưa trích xuất được danh sách ban lãnh đạo từ nguồn công khai trong lần chạy này."
        table_rows = []
        for item in rows[:8]:
            if not isinstance(item, dict):
                continue
            table_rows.append(
                (
                    item.get("name"),
                    item.get("position") or item.get("title"),
                    item.get("shares"),
                    item.get("ownership_percent") if item.get("ownership_percent") is not None else item.get("ratio"),
                    item.get("ownership_note") or item.get("ownership_source") or self._source_display(item.get("source")),
                )
            )
        return self._simple_table(["Họ tên", "Chức vụ", "Số cổ phiếu", "Tỷ lệ sở hữu", "Ghi chú"], table_rows)

    def _ownership_markdown(self, rows: Any) -> str:
        if not isinstance(rows, list) or not rows:
            return "Chưa trích xuất được dữ liệu sở hữu đáng tin cậy từ nguồn công khai trong lần chạy này."
        table_rows = []
        for item in rows[:8]:
            if not isinstance(item, dict):
                continue
            table_rows.append(
                (
                    item.get("holder") or item.get("name"),
                    item.get("shares"),
                    item.get("ownership_percent") or item.get("ratio"),
                    self._source_display(item.get("source")),
                )
            )
        return self._simple_table(["Cổ đông / Tổ chức / Cá nhân", "Số cổ phiếu", "Tỷ lệ sở hữu", "Ghi chú"], table_rows)

    def _market_context_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        view = self._dict(presentation.get("market_context_view"))
        lines = [self._text(view.get("narrative") or presentation.get("market_context"), "Bối cảnh thị trường cần được đối chiếu thêm.")]
        cards = view.get("cards")
        if isinstance(cards, list) and cards:
            rows = [(self._value(card.get("label")), self._value(card.get("value"))) for card in cards if isinstance(card, dict)]
            lines.extend(["", self._simple_table(["Yếu tố", "Giá trị"], rows)])
        if view.get("display_date") or view.get("source"):
            lines.append("")
            lines.append(f"**Cập nhật:** {self._value(view.get('display_date'))} | **Nguồn:** {self._value(view.get('source'))}")
        return "\n".join(lines)

    def _price_momentum_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        momentum = self._dict(summary.get("momentum"))
        rows = [
            ("Giá đóng cửa gần nhất", self._first_value(latest, "close_price", "close", "last_price", "price")),
            ("Khối lượng gần nhất", self._first_value(latest, "volume", "total_volume", "trading_volume")),
            ("Biến động kỳ chart", momentum.get("change_pct")),
            ("Số điểm dữ liệu giá", momentum.get("period_points")),
            ("Giá đầu kỳ chart", momentum.get("first_close")),
            ("Giá cuối kỳ chart", momentum.get("last_close")),
        ]
        return "\n\n".join(
            [
                self._text(presentation.get("price_momentum"), "Chuỗi giá cần được đối chiếu thêm."),
                self._simple_table(["Chỉ tiêu", "Giá trị"], [(label, self._value(value)) for label, value in rows]),
            ]
        )

    def _financial_analysis_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        periods = bctc.get("periods")
        lines = [self._text(presentation.get("financial_analysis"), "Bộ dữ liệu BCTC hiện chưa đủ để phân tích sâu.")]
        if isinstance(periods, list) and periods:
            if self._has_bank_metrics(periods):
                lines.extend(["", self._bank_financial_table(periods)])
            else:
                rows = []
                for period in periods:
                    if isinstance(period, dict):
                        rows.append(
                            (
                                period.get("period"),
                                period.get("revenue"),
                                period.get("gross_profit"),
                                period.get("profit_before_tax"),
                                period.get("profit_after_tax") or period.get("parent_profit"),
                                period.get("eps"),
                                self._financial_value(period, "total_assets"),
                                period.get("total_liabilities"),
                                self._financial_value(period, "equity"),
                                period.get("pe"),
                                period.get("pb"),
                                self._financial_value(period, "roe"),
                                self._financial_value(period, "roa"),
                            )
                        )
                lines.extend(["", self._simple_table(["Kỳ", "Doanh thu", "LN gộp", "LNTT", "LNST", "EPS", "Tổng tài sản", "Nợ phải trả", "Vốn chủ", "P/E", "P/B", "ROE", "ROA"], rows)])
        financial_balance = self._dict(summary.get("financial_balance"))
        if financial_balance:
            if self._has_bank_metrics([financial_balance]):
                balance_rows = [
                    ("Tổng tài sản", self._financial_value(financial_balance, "total_assets")),
                    ("Cho vay khách hàng", self._financial_value(financial_balance, "customer_loans")),
                    ("Tiền gửi khách hàng", self._financial_value(financial_balance, "customer_deposits")),
                    ("Tiền gửi tại NHNN", financial_balance.get("deposit_at_state_bank")),
                    ("Chứng khoán đầu tư", financial_balance.get("investment_securities")),
                    ("Phát hành giấy tờ có giá", financial_balance.get("valuable_papers_issued")),
                    ("Vốn chủ sở hữu", self._financial_value(financial_balance, "equity")),
                    ("P/E", financial_balance.get("pe")),
                    ("P/B", financial_balance.get("pb")),
                    ("ROE", self._financial_value(financial_balance, "roe")),
                    ("ROA", self._financial_value(financial_balance, "roa")),
                ]
            else:
                balance_rows = [
                    ("Tổng tài sản", self._financial_value(financial_balance, "total_assets")),
                    ("Nợ phải trả", financial_balance.get("total_liabilities")),
                    ("Vốn chủ sở hữu", self._financial_value(financial_balance, "equity")),
                    ("Tài sản ngắn hạn", financial_balance.get("current_assets")),
                    ("Nợ ngắn hạn", financial_balance.get("current_liabilities")),
                    ("Tiền và tương đương tiền", financial_balance.get("cash")),
                    ("Hàng tồn kho", financial_balance.get("inventory")),
                    ("P/E", financial_balance.get("pe")),
                    ("P/B", financial_balance.get("pb")),
                    ("ROE", self._financial_value(financial_balance, "roe")),
                ]
            lines.extend(["", "**Sức khỏe bảng cân đối kỳ gần nhất**", "", self._simple_table(["Chỉ tiêu", "Giá trị"], balance_rows)])
        if not (isinstance(periods, list) and periods) and not financial_balance:
            lines.append("")
            lines.append("Chưa đủ dữ liệu xác thực để lập bảng tài chính định lượng. Báo cáo không suy diễn doanh thu, lợi nhuận hoặc bảng cân đối khi chưa có số liệu kiểm chứng.")
        return "\n".join(lines)

    def _valuation_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        scores = self._dict(summary.get("scores"))
        rows = [
            ("EPS", self._first_value(latest, "eps")),
            ("P/E", self._first_value(latest, "pe", "pe_ratio")),
            ("Forward P/E", self._first_value(latest, "forward_pe")),
            ("P/B", self._first_value(latest, "pb", "pb_ratio")),
            ("BVPS", self._first_value(latest, "bvps")),
            ("ROE", self._first_value(latest, "roe")),
            ("Điểm định giá", scores.get("valuation_score")),
        ]
        return "\n\n".join(
            [
                self._text(presentation.get("valuation"), "Chưa đủ dữ liệu định giá xác thực."),
                self._simple_table(["Yếu tố", "Dữ liệu"], [(label, self._value(value)) for label, value in rows]),
            ]
        )

    def _peer_comparison_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        context = self._dict(summary.get("industry_peer_context"))
        industry = self._dict(context.get("industry"))
        peers = context.get("peers")
        lines = [
            self._text(presentation.get("peer_note"), "Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận."),
            "",
            "Bảng này dùng để so sánh mã đang phân tích với các doanh nghiệp cùng nhóm ngành. Các chỉ tiêu như vốn hóa, P/E, P/B, ROE và thanh khoản giúp đọc tương quan quy mô, định giá và hiệu quả sinh lời; đây là danh sách tham khảo để theo dõi, không phải khuyến nghị mua/bán cá nhân hóa.",
            "",
            "**Cách đọc nhanh:** P/E là mức giá thị trường đang trả cho mỗi đồng lợi nhuận; P/B so với giá trị sổ sách; ROE là hiệu quả sinh lời trên vốn chủ; vốn hóa là quy mô thị trường; thanh khoản là mức độ dễ mua/bán.",
        ]
        if industry:
            rows = [
                ("Ngành cấp cao", industry.get("sector") or industry.get("sector_name")),
                ("Nhóm ngành", industry.get("industry") or industry.get("industry_name")),
                ("Nguồn", industry.get("source")),
            ]
            lines.extend(["", "**Ngành/nhóm tham chiếu**", "", self._simple_table(["Nội dung", "Giá trị"], rows)])
        if isinstance(peers, list) and peers:
            rows = []
            for peer in peers:
                if isinstance(peer, dict):
                    rows.append(
                        (
                            peer.get("symbol"),
                            peer.get("company") or peer.get("company_name"),
                            peer.get("close_price") or peer.get("price"),
                            peer.get("change_1d_percent"),
                            peer.get("matched_value_billion"),
                            peer.get("market_cap_billion") or peer.get("market_cap"),
                            peer.get("eps_4q"),
                            peer.get("pe_basic") or peer.get("pe"),
                            peer.get("pb"),
                            peer.get("roe"),
                            peer.get("buy_sell_signal"),
                            self._peer_comment(peer),
                        )
                    )
            lines.extend(["", self._simple_table(["Mã", "Doanh nghiệp", "Giá", "% 1D", "GT giao dịch", "Vốn hóa", "EPS 4Q", "P/E", "P/B", "ROE", "Tín hiệu", "Nhận xét"], rows)])
        return "\n".join(lines)

    def _reference_candidates_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        candidates = presentation.get("reference_candidates")
        if isinstance(candidates, list) and candidates:
            rows = []
            for candidate in candidates:
                if isinstance(candidate, dict):
                    rows.append(
                        (
                            candidate.get("ticker"),
                            candidate.get("company"),
                            candidate.get("reason_to_watch"),
                            candidate.get("strengths") or self._supporting_data_text(self._dict(candidate.get("supporting_data"))),
                            candidate.get("key_risk"),
                            candidate.get("available_data") or self._supporting_data_text(self._dict(candidate.get("supporting_data"))),
                            candidate.get("missing_data") or "Cần bổ sung peer/đơn vị/nguồn gốc nếu còn trống",
                            self._format_confidence(candidate.get("confidence")),
                            self._source_display(candidate.get("source")),
                        )
                    )
            return self._simple_table(["Mã", "Doanh nghiệp", "Lý do theo dõi", "Điểm mạnh", "Rủi ro", "Dữ liệu đã có", "Dữ liệu còn thiếu", "Tỷ lệ tin cậy", "Nguồn"], rows)
        return "Chưa đủ dữ liệu xác thực để đưa ra mã tham khảo cùng nhóm/ngành. Báo cáo không tự tạo danh sách peer nếu nguồn dữ liệu chưa xác nhận."

    def _research_insights_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        insights = self._dict(presentation.get("research_insights"))
        context = self._dict(summary.get("external_research_context"))
        note = self._text(context.get("note"), "Tin tức bên ngoài chỉ là bằng chứng ngữ cảnh; cần kiểm chứng URL gốc.")
        lines = [
            f"**Ghi chú:** {note}",
            "",
            self._text(insights.get("synthesis"), "Chưa có đủ tin tức/nghiên cứu bên ngoài đã được xác thực để bổ sung vào luận điểm."),
            "",
        ]
        groups = [
            ("Catalyst tích cực", insights.get("positive_catalysts")),
            ("Rủi ro/tín hiệu cần thận trọng", insights.get("risks")),
            ("Bối cảnh ngành/thông tin nền", insights.get("background")),
            ("Cần kiểm chứng", insights.get("needs_verification")),
        ]
        any_item = False
        for label, items in groups:
            if isinstance(items, list) and items:
                any_item = True
                lines.extend([f"**{label}**", "", self._research_items_block(items), ""])
        if not any_item:
            lines.append("Chưa có đủ tin tức/nghiên cứu bên ngoài đã được xác thực để bổ sung vào luận điểm.")
        return "\n".join(lines).strip()

    def _research_items_block(self, items: list[dict[str, Any]]) -> str:
        blocks = []
        for item in items[:6]:
            if not isinstance(item, dict):
                continue
            blocks.append(
                "\n".join(
                    [
                        f"- **{self._markdown_link(item.get('title'), item.get('url'))}**",
                        f"  - Nguồn/ngày: {self._source_display(item.get('source'))} · {self._value(item.get('display_date') or self._format_datetime(item.get('published_at')))}",
                        f"  - Tóm tắt: {self._value(item.get('detailed_summary'))}",
                        f"  - Vì sao đáng chú ý: {self._value(item.get('why_it_matters'))}",
                        f"  - Tác động có thể có: {self._value(item.get('possible_impact'))}",
                        f"  - Cần kiểm chứng: {self._value(item.get('what_to_verify'))}",
                    ]
                )
            )
        return "\n".join(blocks) if blocks else "Chưa có mục phù hợp."

    def _professional_score_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        cards = presentation.get("score_cards")
        if isinstance(cards, list) and cards:
            rows = [
                (
                    card.get("label"),
                    card.get("display_value") or (self._format_confidence(card.get("score")) if card.get("key") == "data_confidence" else card.get("score")),
                    card.get("tag") or card.get("score_label"),
                    card.get("description") or card.get("reason"),
                    card.get("data_used"),
                    card.get("could_improve"),
                )
                for card in cards
                if isinstance(card, dict)
            ]
            return self._simple_table(["Nhóm điểm", "Điểm", "Nhãn", "Diễn giải", "Dữ liệu dùng", "Yếu tố cải thiện/giảm điểm"], rows)
        return self._friendly_score_table(summary) + "\n\n" + self._score_explanation_block(summary)

    def _roadmap_section(self, presentation: dict[str, Any]) -> str:
        roadmap = presentation.get("roadmap")
        if isinstance(roadmap, list) and roadmap:
            keys = ["phase", "horizon", "focus"]
            rows = [tuple(self._value(item.get(key)) for key in keys) for item in roadmap if isinstance(item, dict)]
            return self._simple_table(keys, rows)
        return "Cần bổ sung dữ liệu giá, BCTC và catalyst để xây dựng lộ trình theo dõi cụ thể hơn."

    def _risk_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        executive = self._dict(presentation.get("executive_summary"))
        risks = self._string_list(executive.get("key_risks")) or self._string_list(summary.get("weaknesses"))
        return self._list_block(None, risks)

    def _data_quality_main_section(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        data_quality = self._dict(presentation.get("data_quality"))
        user_notes = self._string_list(data_quality.get("user_notes"))
        coverage_rows = presentation.get("coverage_rows")
        lines = [
            "Phần này tóm tắt giới hạn dữ liệu theo cách phục vụ quyết định phân tích. Chi tiết kỹ thuật được đặt ở phụ lục.",
            "",
            self._list_block("Ghi chú dữ liệu", user_notes),
            "",
            self._coverage_rows_table(coverage_rows) if isinstance(coverage_rows, list) else self._friendly_coverage_table(self._dict(summary.get("data_coverage"))),
        ]
        return "\n".join(lines)

    def _appendix_section(self, summary: dict[str, Any]) -> str:
        context = self._dict(summary.get("external_research_context"))
        items = context.get("items") if isinstance(context.get("items"), list) else []
        data_quality = self._dict(self._dict(summary.get("report_presentation")).get("data_quality"))
        user_notes = self._string_list(data_quality.get("user_notes")) or self._string_list(summary.get("data_quality_notes"))
        lines = [
            "### Nguồn tin tức/nghiên cứu",
            "",
            self._external_sources_table(items),
            "",
            "### Độ phủ dữ liệu",
            "",
            self._friendly_coverage_table(self._dict(summary.get("data_coverage"))),
            "",
            "### Ghi chú giới hạn",
            "",
            self._list_block(None, user_notes),
            "",
            "### Từ điển chỉ số",
            "",
            self._metric_dictionary(),
        ]
        return "\n".join(lines)

    def _external_sources_table(self, items: list[Any]) -> str:
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    self._source_display(item.get("source")),
                    self._markdown_link(item.get("title"), item.get("url")),
                    self._format_datetime(item.get("published_at")),
                    self._value(item.get("tone")),
                )
            )
        return self._simple_table(["Nguồn", "Tiêu đề", "Ngày", "Sắc thái"], rows) if rows else "Chưa có nguồn tin bên ngoài được sử dụng."

    def _kpi_table(self, summary: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        financial = self._dict(summary.get("financial_balance"))
        momentum = self._dict(summary.get("momentum"))
        rows = [
            ("Giá đóng cửa", self._first_value(latest, "close_price", "close", "last_price", "price")),
            ("Khối lượng", self._first_value(latest, "volume", "total_volume", "trading_volume")),
            ("EPS", self._first_value(latest, "eps", "EPS") or self._first_value(financial, "eps", "EPS")),
            ("P/E", self._first_value(latest, "pe", "pe_ratio", "PE") or self._first_value(financial, "pe", "pe_ratio", "PE")),
            ("P/B", self._first_value(latest, "pb", "pb_ratio", "PB") or self._first_value(financial, "pb", "pb_ratio", "PB")),
            ("ROE", self._first_value(latest, "roe", "ROE") or self._first_value(financial, "roe", "ROE")),
            ("Momentum kỳ chart", momentum.get("change_pct")),
            ("Số điểm chart", momentum.get("period_points")),
        ]
        return self._simple_table(["Chỉ số", "Giá trị"], [(name, self._value(value)) for name, value in rows])

    def _fallback_score_cards(self, scores: dict[str, Any]) -> list[dict[str, Any]]:
        definitions = [
            ("valuation_score", "Định giá", "P/E, forward P/E, P/B và ROE nếu có."),
            ("quality_score", "Chất lượng", "ROE, ROS, ROAA và lợi nhuận sau thuế nếu có."),
            ("growth_score", "Tăng trưởng", "Xu hướng doanh thu/lợi nhuận qua các kỳ tài chính."),
            ("momentum_score", "Động lượng giá", "Biến động giá trong chuỗi giá hiện có."),
            ("liquidity_score", "Thanh khoản", "Khối lượng và giá trị giao dịch ước tính."),
            ("size_score", "Quy mô", "Vốn hóa thị trường nếu dữ liệu có sẵn."),
            ("risk_score", "Rủi ro", "Beta, volatility/drawdown, bối cảnh thị trường và dữ liệu còn thiếu."),
        ]
        cards = []
        for key, label, data_used in definitions:
            score = scores.get(key)
            cards.append(
                {
                    "key": key,
                    "label": label,
                    "score": score,
                    "meter_percent": score if isinstance(score, (int, float)) else None,
                    "display_value": str(score) if score is not None else None,
                    "scale": "0-100",
                    "score_label": self._score_label(score, inverse=(key == "risk_score")),
                    "reason": "Điểm được tính từ các dữ liệu định lượng hiện có.",
                    "data_used": data_used,
                    "could_improve": "Cần bổ sung dữ liệu nhiều kỳ, peer và nguồn gốc để tăng độ tin cậy.",
                }
            )
        if "score_confidence" in scores:
            cards.append(
                {
                    "key": "data_confidence",
                    "label": "Tỷ lệ tin cậy dữ liệu",
                    "score": normalize_percent_score(scores.get("score_confidence")),
                    "meter_percent": normalize_percent_score(scores.get("score_confidence")),
                    "display_value": self._format_confidence(scores.get("score_confidence")),
                    "unit": "%",
                    "scale": "0-100",
                    "score_label": "Cần đọc cùng độ phủ dữ liệu",
                    "reason": "Phản ánh độ phủ giá, tài chính, thị trường, peer và nguồn nghiên cứu.",
                    "data_used": "Độ phủ dữ liệu và ghi chú chất lượng.",
                    "could_improve": "Cải thiện khi có thêm BCTC, peer và nguồn nghiên cứu xác thực.",
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

    def _friendly_score_table(self, summary: dict[str, Any]) -> str:
        scores = self._dict(summary.get("scores"))
        if not scores:
            return "Chưa có dữ liệu điểm số."
        rows = [
            ("Định giá", scores.get("valuation_score")),
            ("Chất lượng", scores.get("quality_score")),
            ("Tăng trưởng", scores.get("growth_score")),
            ("Động lượng giá", scores.get("momentum_score")),
            ("Thanh khoản", scores.get("liquidity_score")),
            ("Quy mô", scores.get("size_score")),
            ("Rủi ro", scores.get("risk_score")),
            ("Nhãn rủi ro", scores.get("risk_label")),
            ("Điểm tổng", scores.get("overall_score")),
            ("Nhãn tổng", scores.get("overall_label")),
            ("Tỷ lệ tin cậy dữ liệu", self._format_confidence(scores.get("score_confidence"))),
        ]
        return self._simple_table(["Nhóm điểm", "Giá trị"], rows)

    def _score_explanation_block(self, summary: dict[str, Any]) -> str:
        explanations = self._string_list(summary.get("score_explanations") or self._dict(summary.get("scores")).get("score_explanations"))
        if not explanations:
            return "Chưa có giải thích điểm số."
        return self._list_block("Giải thích scoring", explanations)

    def _coverage_table(self, summary: dict[str, Any]) -> str:
        coverage = self._dict(summary.get("data_coverage"))
        if not coverage:
            return "Chưa có dữ liệu độ phủ."
        return self._simple_table(["Nguồn/trường", "Trạng thái"], [(key, self._value(value)) for key, value in coverage.items()])

    def _friendly_coverage_table(self, coverage: dict[str, Any]) -> str:
        rows = [
            ("Dữ liệu giá mới nhất", self._coverage_status(coverage.get("latest_price_loaded"))),
            ("Chuỗi giá", f"{self._value(coverage.get('price_history_points'))} điểm dữ liệu"),
            (
                "Báo cáo tài chính",
                self._coverage_status(
                    coverage.get("financials_loaded") or coverage.get("financial_ratios_loaded"),
                    count=coverage.get("financial_periods_count") or coverage.get("financial_ratio_periods_count"),
                ),
            ),
            ("Bối cảnh thị trường", self._coverage_status(coverage.get("market_context_loaded"))),
            ("So sánh peer", self._coverage_status(coverage.get("peer_context_loaded"))),
            ("Tin tức/nghiên cứu", f"{self._value(coverage.get('external_research_items'))} nguồn phù hợp"),
        ]
        return self._simple_table(["Nhóm dữ liệu", "Tình trạng"], rows)

    def _coverage_rows_table(self, rows: list[Any]) -> str:
        table_rows = []
        for row in rows:
            if isinstance(row, dict):
                table_rows.append((row.get("label") or row.get("group"), row.get("status_label") or row.get("status"), row.get("description") or row.get("note")))
        return self._simple_table(["Nhóm dữ liệu", "Tình trạng", "Ghi chú"], table_rows) if table_rows else "Chưa có bảng độ phủ dữ liệu."

    def _supporting_data_text(self, data: dict[str, Any]) -> str:
        parts = []
        labels = {
            "close_price": "Giá",
            "change_1d_percent": "% 1D",
            "matched_value_billion": "GT khớp lệnh",
            "market_cap_billion": "Vốn hóa",
            "eps_4q": "EPS 4Q",
            "pe_basic": "P/E",
            "pe": "P/E",
            "pb": "P/B",
            "roe": "ROE",
            "rsi_14": "RSI",
            "basic_score": "Điểm cơ bản",
            "fundamental_rating": "Xếp hạng",
            "momentum_1m": "Momentum 1M",
        }
        for key, label in labels.items():
            if data.get(key) not in (None, ""):
                parts.append(f"{label}: {self._value(data.get(key))}")
        return "; ".join(parts) if parts else "Chưa có chỉ tiêu định lượng đã xác minh"

    def _coverage_status(self, value: Any, count: Any | None = None) -> str:
        if value is True:
            if isinstance(count, int):
                return f"Đã có ({count} kỳ)"
            return "Đã có"
        if value is False:
            return "Chưa đủ dữ liệu xác thực"
        return "Cần kiểm tra thêm"

    def _research_section(self, summary: dict[str, Any]) -> str:
        context = self._dict(summary.get("external_research_context"))
        note = self._text(context.get("note"), "Tin tức bên ngoài chỉ là bằng chứng ngữ cảnh; cần kiểm chứng URL gốc.")
        items = context.get("items") if isinstance(context.get("items"), list) else []
        lines = [f"**Ghi chú:** {note}", ""]
        if not items:
            lines.append("Chưa có dữ liệu")
            return "\n".join(lines)

        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            flags = []
            flags.extend(item.get("positive_flags") or [])
            flags.extend(item.get("negative_flags") or [])
            flags.extend(item.get("catalyst_flags") or [])
            rows.append(
                (
                    self._text(item.get("source"), "Chưa rõ nguồn"),
                    self._markdown_link(item.get("title"), item.get("url")),
                    self._format_datetime(item.get("published_at")),
                    self._text(item.get("tone"), "Chưa có dữ liệu"),
                    ", ".join(flags) if flags else "Chưa có dữ liệu",
                    self._text(item.get("snippet"), "Chưa có dữ liệu"),
                )
            )
        if not rows:
            lines.append("Chưa có dữ liệu")
            return "\n".join(lines)
        lines.append(self._simple_table(["Nguồn", "Tiêu đề/URL", "Ngày", "Tone", "Flags", "Trích yếu"], rows))
        return "\n".join(lines)

    def _investment_memo(self, summary: dict[str, Any], llm_narrative: str | None) -> str:
        decision = self._dict(summary.get("system_decision"))
        lines = [
            f"- **Luận điểm chính:** {self._text(decision.get('action'), 'Cần kiểm tra thêm')}",
            f"- **Mức độ chắc chắn:** {self._text(decision.get('status'), 'Chưa có dữ liệu')}",
            f"- **Rủi ro dữ liệu:** {self._text('; '.join(self._string_list(summary.get('data_quality_notes'))), 'Chưa có dữ liệu')}",
        ]
        if llm_narrative:
            lines.extend(["", "**Diễn giải LLM đã kiểm soát:**", "", llm_narrative])
        return "\n".join(lines)

    def _financial_statement_section(self, summary: dict[str, Any]) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        periods = bctc.get("periods")
        notes = self._string_list(bctc.get("data_quality_notes"))
        if isinstance(periods, list) and periods:
            keys = [
                "period",
                "revenue",
                "gross_profit",
                "operating_profit",
                "profit_before_tax",
                "profit_after_tax",
                "parent_profit",
                "eps",
                "total_assets",
                "total_liabilities",
                "equity",
            ]
            rows = []
            for period in periods[:6]:
                if isinstance(period, dict):
                    rows.append(tuple(self._value(period.get(key)) for key in keys))
            financial_balance = self._dict(summary.get("financial_balance"))
            balance_block = ""
            if financial_balance:
                balance_block = "\n\n**Bảng cân đối/tài chính mới nhất:**\n\n" + self._dict_table(financial_balance)
            return self._simple_table(keys, rows) + balance_block

        financial = self._dict(summary.get("financial_balance"))
        if financial:
            return self._dict_table(financial)
        if notes:
            return self._list_block("Ghi chú dữ liệu BCTC", notes)
        return "Chưa có dữ liệu"

    def _legacy_peer_comparison_section(self, summary: dict[str, Any]) -> str:
        context = self._dict(summary.get("industry_peer_context"))
        industry = self._dict(context.get("industry"))
        peers = context.get("peers")
        lines: list[str] = []
        if industry:
            lines.extend(["**Ngành:**", "", self._dict_table(industry), ""])
        if isinstance(peers, list) and peers:
            keys = ["symbol", "company", "exchange", "close_price", "pe", "pb", "roe", "market_cap", "profit_after_tax", "revenue", "momentum_1m"]
            rows = []
            for peer in peers:
                if isinstance(peer, dict):
                    rows.append(tuple(self._value(peer.get(key)) for key in keys))
            lines.append(self._simple_table(keys, rows))
        else:
            lines.append("Chưa có dữ liệu peer cùng ngành.")
        return "\n".join(lines)

    def _same_industry_section(self, summary: dict[str, Any]) -> str:
        recommendation = self._dict(summary.get("same_industry_recommendation"))
        candidates = recommendation.get("candidates")
        lines: list[str] = []
        method = recommendation.get("method")
        if method:
            lines.append(f"**Phương pháp:** {self._text(method, 'Cần kiểm tra thêm')}")
            lines.append("")
        if isinstance(candidates, list) and candidates:
            keys = ["symbol", "company", "close_price", "pe", "pb", "roe", "market_cap", "momentum_1m"]
            rows = []
            for item in candidates:
                if isinstance(item, dict):
                    rows.append(tuple(self._value(item.get(key)) for key in keys))
            lines.append(self._simple_table(keys, rows))
        elif recommendation:
            lines.append(self._dict_table(recommendation))
        else:
            lines.append("Chưa có dữ liệu peer cùng ngành đủ tin cậy để đề xuất mã thay thế.")
        return "\n".join(lines)

    def _valuation_quality_section(self, summary: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        financial = self._dict(summary.get("financial_balance"))
        rows = [
            ("EPS", self._first_value(latest, "eps") or self._first_value(financial, "eps")),
            ("P/E", self._first_value(latest, "pe", "pe_ratio") or self._first_value(financial, "pe", "pe_ratio")),
            ("P/B", self._first_value(latest, "pb", "pb_ratio") or self._first_value(financial, "pb", "pb_ratio")),
            ("ROE", self._first_value(latest, "roe") or self._first_value(financial, "roe")),
        ]
        table = self._simple_table(["Yếu tố", "Dữ liệu"], [(name, self._value(value)) for name, value in rows])
        return f"{table}\n\nCần kiểm tra thêm chất lượng lợi nhuận, dòng tiền và thuyết minh BCTC nếu dữ liệu hiện có chưa đầy đủ."

    def _entry_plan_section(self, summary: dict[str, Any]) -> str:
        plan = self._dict(summary.get("investment_plan"))
        action_table = plan.get("action_table")
        lines: list[str] = []
        if isinstance(action_table, list) and action_table:
            rows = []
            for item in action_table:
                if isinstance(item, dict):
                    rows.append((self._value(item.get("time")), self._value(item.get("action")), self._value(item.get("condition"))))
            lines.append(self._simple_table(["Thời điểm", "Hành động", "Điều kiện"], rows))
        else:
            lines.append("Cần kiểm tra thêm dữ liệu kỹ thuật, thanh khoản, vùng hỗ trợ/kháng cự và biến động thị trường trước khi vào vị thế.")

        position = self._dict(plan.get("position_sizing"))
        if position:
            lines.extend(["", self._simple_table(["Thông số quản trị vốn", "Giá trị"], [(key, self._value(value)) for key, value in position.items()])])
        return "\n".join(lines)

    def _holding_plan_section(self, summary: dict[str, Any]) -> str:
        plan = self._dict(summary.get("investment_plan"))
        rows = [
            ("Luận điểm nắm giữ", self._value(self._dict(plan.get("decision")).get("holding_thesis"))),
            ("Rủi ro cần theo dõi", self._value(self._dict(plan.get("decision")).get("key_risk"))),
            ("Điều kiện đánh giá lại", self._value(self._dict(plan.get("decision")).get("review_condition"))),
        ]
        table = self._simple_table(["Nội dung", "Ghi chú"], rows)
        return f"{table}\n\nNếu các trường trên chưa có dữ liệu, cần bổ sung dữ liệu kế hoạch kinh doanh, BCTC nhiều kỳ và catalyst doanh nghiệp."

    def _scenario_matrix(self, summary: dict[str, Any]) -> str:
        scenario = summary.get("scenario_matrix")
        if isinstance(scenario, list) and scenario:
            rows = []
            for item in scenario:
                if isinstance(item, dict):
                    rows.append((self._value(item.get("scenario")), self._value(item.get("condition")), self._value(item.get("response"))))
            return self._simple_table(["Kịch bản", "Điều kiện", "Ứng xử"], rows)
        return self._simple_table(
            ["Kịch bản", "Điều kiện cần kiểm tra", "Ứng xử tham khảo"],
            [
                ("Tích cực", "Dữ liệu giá, thanh khoản, kết quả kinh doanh và tin tức xác nhận cùng chiều.", "Cần kiểm tra thêm trước khi tăng tỷ trọng."),
                ("Cơ sở", "Dữ liệu chưa đủ để xác nhận xu hướng mạnh.", "Theo dõi và giữ kỷ luật quản trị vốn."),
                ("Tiêu cực", "Tin xấu, suy giảm lợi nhuận, thanh khoản yếu hoặc thị trường chung xấu đi.", "Giảm rủi ro theo kế hoạch đã xác định."),
            ],
        )

    def _checklist(self, summary: dict[str, Any]) -> str:
        research = self._dict(summary.get("external_research_context"))
        items = [
            "Đối chiếu giá, volume, EPS, P/E, P/B, ROE với nguồn dữ liệu gốc.",
            "Mở các URL tin tức/nghiên cứu bên ngoài để xác nhận tiêu đề, ngày đăng và nội dung.",
            "Kiểm tra BCTC, dòng tiền, nợ vay và thuyết minh nếu dữ liệu hiện có chưa đầy đủ.",
            "Xác định mức vốn, mức rủi ro mỗi giao dịch và tỷ trọng tối đa trước khi đặt lệnh.",
            "Không xem báo cáo này là khuyến nghị đầu tư cá nhân hóa.",
        ]
        if not research.get("items"):
            items.append("Nguồn nghiên cứu bên ngoài đang trống; cần kiểm tra thêm tin tức mới nhất bằng nguồn độc lập.")
        return "\n".join(f"- [ ] {item}" for item in items)

    def _metric_dictionary(self) -> str:
        return self._simple_table(
            ["Chỉ số", "Cách đọc"],
            [
                ("Giá đóng cửa", "Giá giao dịch cuối kỳ/phiên từ nguồn dữ liệu gốc."),
                ("Khối lượng", "Khối lượng giao dịch; dùng để kiểm tra thanh khoản và độ tin cậy của biến động giá."),
                ("EPS", "Lợi nhuận trên mỗi cổ phiếu; cần đối chiếu kỳ tính và nguồn dữ liệu."),
                ("P/E", "Giá trên lợi nhuận; thấp/cao cần so với ngành và chất lượng lợi nhuận."),
                ("P/B", "Giá trên giá trị sổ sách; cần đọc cùng ROE và đặc thù ngành."),
                ("ROE", "Lợi nhuận trên vốn chủ sở hữu; phản ánh hiệu quả sử dụng vốn nếu dữ liệu đáng tin cậy."),
                ("Momentum", "Biến động giá trong chuỗi giá hiện có, không phải dự báo chắc chắn."),
                ("Tone tin tức", "Phân loại keyword đơn giản: tích cực, tiêu cực, hỗn hợp hoặc trung tính."),
            ],
        )

    def _dict_table(self, data: dict[str, Any], empty_text: str = "Chưa có dữ liệu") -> str:
        if not data:
            return empty_text
        return self._simple_table(["Trường", "Giá trị"], [(key, self._value(value)) for key, value in data.items()])

    def _simple_table(self, headers: list[str], rows: list[tuple[Any, ...]]) -> str:
        if not rows:
            return "Chưa đủ dữ liệu xác thực"
        header_line = "| " + " | ".join(self._escape_cell(header) for header in headers) + " |"
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        body = []
        for row in rows:
            padded = list(row) + [""] * max(len(headers) - len(row), 0)
            body.append("| " + " | ".join(self._escape_cell(value) for value in padded[: len(headers)]) + " |")
        return "\n".join([header_line, separator, *body])

    def _list_block(self, title: str | None, values: Any) -> str:
        items = self._string_list(values)
        prefix = f"**{title}:**\n\n" if title else ""
        if not items:
            return f"{prefix}Chưa đủ dữ liệu xác thực"
        return prefix + "\n".join(f"- {item}" for item in items)

    def _markdown_link(self, title: Any, url: Any) -> str:
        clean_title = self._text(title, "Chưa có tiêu đề").replace("[", "\\[").replace("]", "\\]")
        clean_url = self._text(url, "")
        if not clean_url:
            return clean_title
        return f"[{clean_title}]({clean_url})"

    def _first_value(self, data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    def _value(self, value: Any) -> str:
        if value is None or value == "":
            return "Chưa xác minh"
        if isinstance(value, bool):
            return "Có" if value else "Không"
        if isinstance(value, (int, float)):
            return f"{value:,}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"
        if isinstance(value, list):
            if not value:
                return "Chưa xác minh"
            return "; ".join(self._value(item) for item in value)
        if isinstance(value, dict):
            if not value:
                return "Chưa xác minh"
            return "; ".join(f"{key}: {self._value(item)}" for key, item in value.items())
        return str(value)

    def _format_confidence(self, value: Any) -> str:
        return format_percent_ratio(value, decimals=0)

    def _has_bank_metrics(self, periods: Any) -> bool:
        if not isinstance(periods, list):
            return False
        bank_keys = {
            "net_interest_income",
            "net_fee_income",
            "pre_provision_operating_profit",
            "credit_provision_expense",
            "customer_loans",
            "customer_deposits",
            "npl_ratio",
            "nim",
            "casa_ratio",
        }
        return any(isinstance(period, dict) and any(period.get(key) is not None for key in bank_keys) for period in periods)

    def _bank_financial_table(self, periods: list[Any]) -> str:
        rows = []
        for period in periods:
            if not isinstance(period, dict):
                continue
            rows.append(
                (
                    period.get("period"),
                    period.get("net_interest_income"),
                    period.get("net_fee_income"),
                    period.get("pre_provision_operating_profit"),
                    period.get("credit_provision_expense"),
                    period.get("profit_before_tax"),
                    period.get("profit_after_tax") or period.get("parent_profit"),
                    period.get("eps"),
                    self._financial_value(period, "total_assets"),
                    self._financial_value(period, "customer_loans"),
                    self._financial_value(period, "customer_deposits"),
                    self._financial_value(period, "equity"),
                    period.get("pe"),
                    period.get("pb"),
                    period.get("nim"),
                    period.get("npl_ratio"),
                    self._financial_value(period, "roe"),
                    self._financial_value(period, "roa"),
                )
            )
        return self._simple_table(
            ["Kỳ", "Thu nhập lãi thuần", "Thu nhập dịch vụ thuần", "LN trước dự phòng", "Dự phòng", "LNTT", "LNST", "EPS", "Tổng tài sản", "Cho vay KH", "Tiền gửi KH", "Vốn chủ", "P/E", "P/B", "NIM", "Nợ xấu", "ROE", "ROA"],
            rows,
        )

    def _financial_value(self, period: dict[str, Any], key: str) -> Any:
        if not isinstance(period, dict):
            return None
        if key in {"total_assets", "equity", "customer_loans", "customer_deposits", "roa", "roe"}:
            return StockDataService.sanitize_financial_period(period).get(key)
        return period.get(key)

    def _peer_comment(self, peer: dict[str, Any]) -> str:
        notes: list[str] = []
        rating = peer.get("fundamental_rating")
        signal = peer.get("buy_sell_signal")
        rsi = peer.get("rsi_14")
        pe = peer.get("pe_basic") or peer.get("pe")
        if rating:
            notes.append(f"Xếp hạng {rating}")
        if signal:
            notes.append(f"Tín hiệu {signal}")
        if isinstance(rsi, (int, float)):
            if rsi < 30:
                notes.append("RSI yếu, cần thận trọng")
            elif rsi > 70:
                notes.append("RSI cao, cần kiểm tra rủi ro quá mua")
        if isinstance(pe, (int, float)) and pe > 0:
            notes.append("Có P/E để so sánh định giá")
        if peer.get("data_note"):
            notes.append(str(peer.get("data_note")))
        elif peer.get("missing_data"):
            notes.append(f"Cần bổ sung: {peer.get('missing_data')}")
        return "; ".join(notes) if notes else "Cần đối chiếu thêm"

    def _format_datetime(self, value: Any) -> str:
        return format_datetime_vi(value, include_time=True)

    def _source_display(self, value: Any) -> str:
        text = str(value or "").strip()
        mapping = {
            "google_news_rss": "Google News",
            "vietstock_via_google_news_rss": "Vietstock",
            "cafef_via_google_news_rss": "CafeF",
            "cafef": "CafeF",
            "google news rss": "Google News",
            "vietstock finance bctt": "Vietstock Finance BCTC",
            "vietstock finance bctc": "Vietstock Finance BCTC",
            "vietstock finance": "Vietstock Finance",
            "cafef bctc": "CafeF BCTC",
            "cafef company overview": "CafeF thông tin doanh nghiệp",
            "cafef thông tin doanh nghiệp": "CafeF thông tin doanh nghiệp",
        }
        return mapping.get(text.lower(), to_user_facing_source_name(text) if text else "Chưa rõ nguồn")

    def _overview_source_value(self, overview: dict[str, Any], industry: dict[str, Any]) -> str:
        note = self._text(overview.get("source_note"), "")
        if note:
            cleaned = re.sub(r"(?i)^nguồn đối chiếu:\s*", "", note).strip()
            cleaned = cleaned[:-1] if cleaned.endswith(".") else cleaned
            if cleaned:
                return cleaned
        if industry.get("source"):
            return self._source_display(industry.get("source"))
        return "Chưa đủ dữ liệu xác thực"

    def _escape_cell(self, value: Any) -> str:
        return self._value(value).replace("|", "\\|").replace("\n", "<br>")

    def _text(self, value: Any, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _sanitize_main_sections(self, markdown: str) -> str:
        return self._sanitize_user_facing_text(markdown)

    def _sanitize_user_facing_text(self, text: str) -> str:
        replacements = [
            (r"\bBackend\b", "nguồn dữ liệu nội bộ"),
            (r"\bService\b", "hệ thống"),
            (r"\bpayload\b", "gói dữ liệu"),
            (r"\bfield\b", "nhóm dữ liệu"),
            (r"\bmodel\b", "mô hình"),
            (r"\bmetadata\b", "thông tin mô tả"),
            (r"industryPeerContext\.peers", "dữ liệu peer"),
            (r"industryPeerContext", "dữ liệu peer"),
            (r"industry_id", "dữ liệu ngành"),
            (r"financials\.periods", "các kỳ báo cáo tài chính"),
            (r"factFinancialStatements", "kho dữ liệu báo cáo tài chính"),
            (r"watchlists token", "quyền truy cập danh sách theo dõi"),
            (r"Không gọi được watchlists[^\n.]*", "Danh sách theo dõi cá nhân chưa được sử dụng trong báo cáo này"),
            (r"\bwatchlists\b", "danh sách theo dõi cá nhân"),
            (r"Stock chưa gắn[^\n.]*", "Dữ liệu phân loại ngành hiện chưa đủ để lập bảng so sánh đáng tin cậy"),
            (r"API failed", "nguồn dữ liệu chưa phản hồi"),
            (r"Client error[^\n.]*", "nguồn dữ liệu chưa phản hồi"),
            (r"/api/[^\s|)]*", "nguồn dữ liệu nội bộ"),
            (r"\bbackend_api\b", "nguồn dữ liệu nội bộ"),
            (r"\bexternal_financial\b", "nguồn tài chính công khai"),
            (r"\bfilesystem\b", "file báo cáo"),
            (r"\bmissing_fields\b", "nhóm dữ liệu còn thiếu"),
            (r"\bMongo\b", "cơ sở dữ liệu nội bộ"),
            (r"\bPlaywright\b", "nguồn dữ liệu công khai"),
            (r"browser rendering", "quá trình tải dữ liệu công khai"),
            (r"render bằng trình duyệt", "đối chiếu từ nguồn công khai"),
            (r"\brender\b", "tải dữ liệu"),
            (r"\bDOM\b", "nội dung trang"),
            (r"\bHTML\b", "nội dung trang"),
            (r"\bselector\b", "vùng dữ liệu"),
            (r"\bcrawl\b", "đối chiếu dữ liệu"),
            (r"\bscrape\b", "đối chiếu dữ liệu"),
            (r"\bBCTT\b", "BCTC"),
            (r"\bNotImplementedError\b", "lỗi môi trường trình duyệt"),
            (r"\bTimeoutError\b", "lỗi timeout nguồn dữ liệu"),
            (r"Chưa có dữ liệu", "Chưa đủ dữ liệu xác thực"),
        ]
        sanitized = text
        for pattern, replacement in replacements:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        return sanitized
