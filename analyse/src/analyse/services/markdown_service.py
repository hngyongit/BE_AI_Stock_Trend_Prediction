from __future__ import annotations

import html
from typing import Any

from analyse.schemas.common import DEFAULT_DISCLAIMER


class MarkdownService:
    """Tạo báo cáo Markdown tiếng Việt từ dữ liệu đã chuẩn hóa."""

    def build(self, summary: dict[str, Any], llm_narrative: str | None = None) -> str:
        symbol = self._text(summary.get("symbol"), "UNKNOWN")
        exchange = self._text(summary.get("scope_exchange"), "HOSE")
        company = self._text(summary.get("company"), "Chưa rõ tên công ty")
        decision = self._dict(summary.get("system_decision"))
        disclaimer = self._text(summary.get("disclaimer"), DEFAULT_DISCLAIMER)

        lines: list[str] = [
            f"# Báo cáo phân tích cổ phiếu {symbol} trên {exchange}",
            "",
            f"**Doanh nghiệp:** {company}",
            "",
            "## 0. Lưu ý và phạm vi",
            "",
            disclaimer,
            "",
            "- Báo cáo dùng dữ liệu định lượng từ Backend và dữ liệu tin tức/nghiên cứu công khai nếu được bật.",
            "- Tin tức bên ngoài chỉ là bằng chứng ngữ cảnh, cần kiểm chứng lại từ URL nguồn trước khi sử dụng.",
            "- Nếu một trường thiếu dữ liệu, báo cáo giữ nguyên mục và ghi rõ “Chưa có dữ liệu” hoặc “Cần kiểm tra thêm”.",
            "",
            "## 1. Kết luận hệ thống: có nên mua không?",
            "",
            f"- **Trạng thái:** {self._text(decision.get('status'), 'CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN')}",
            f"- **Hành động tham khảo:** {self._text(decision.get('action'), 'Cần kiểm tra thêm')}",
            f"- **Ghi chú:** {self._text(decision.get('note'), disclaimer)}",
            "",
            self._list_block("Lý do hệ thống", decision.get("reasons")),
            "",
            self._list_block("Điểm chặn dữ liệu/quyết định", decision.get("blockers")),
            "",
            "## 1A. Bản đồ thị trường HoSE",
            "",
            self._dict_table(self._dict(summary.get("hose_market_context")), empty_text="Chưa có dữ liệu thị trường HoSE/VNINDEX."),
            "",
            "## 1B. Mã cùng ngành phù hợp để mua hiện tại",
            "",
            self._same_industry_section(summary),
            "",
            "## 1C. Nghiên cứu tin tức/ngành/thị trường bên ngoài",
            "",
            self._research_section(summary),
            "",
            "## 1D. Investment memo chuyên nghiệp",
            "",
            self._investment_memo(summary, llm_narrative),
            "",
            "## 2. Dữ liệu đầu vào và độ phủ",
            "",
            self._coverage_table(summary),
            "",
            "## 3. Bối cảnh VNINDEX/HoSE",
            "",
            self._dict_table(self._dict(summary.get("market_general_context")) or self._dict(summary.get("hose_market_context")), empty_text="Chưa có dữ liệu bối cảnh thị trường tổng hợp."),
            "",
            "## 4. So sánh peer cùng ngành",
            "",
            self._peer_comparison_section(summary),
            "",
            "## 5. Dashboard chỉ số chính",
            "",
            self._kpi_table(summary),
            "",
            self._score_table(summary),
            "",
            self._score_explanation_block(summary),
            "",
            "## 6. Phân tích BCTT kỳ chọn",
            "",
            self._financial_statement_section(summary),
            "",
            "## 7. Định giá và chất lượng lợi nhuận",
            "",
            self._valuation_quality_section(summary),
            "",
            "## 8. Kế hoạch vào vị thế 4-5 tuần",
            "",
            self._entry_plan_section(summary),
            "",
            "## 9. Kế hoạch nắm giữ 1-2 năm",
            "",
            self._holding_plan_section(summary),
            "",
            "## 10. Điểm mạnh cụ thể",
            "",
            self._list_block(None, summary.get("strengths")),
            "",
            "## 11. Điểm yếu/rủi ro cụ thể",
            "",
            self._list_block(None, summary.get("weaknesses")),
            "",
            "## 12. Ma trận kịch bản",
            "",
            self._scenario_matrix(summary),
            "",
            "## 13. Checklist trước khi đặt lệnh",
            "",
            self._checklist(summary),
            "",
            "## 14. Từ điển chỉ số, đơn vị và cách đọc",
            "",
            self._metric_dictionary(),
        ]
        return "\n".join(lines).strip() + "\n"

    def finalize_content(self, content: str | None, summary: dict[str, Any]) -> str | None:
        if not content or not content.strip():
            return None
        disclaimer = self._text(summary.get("disclaimer"), DEFAULT_DISCLAIMER)
        narrative = content.strip()
        narrative = narrative.replace(disclaimer, "").strip()
        return html.escape(narrative, quote=False) if narrative else None

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

    def _score_table(self, summary: dict[str, Any]) -> str:
        scores = self._dict(summary.get("scores"))
        if not scores:
            return "Chưa có dữ liệu điểm số."
        display_keys = [
            "valuation_score",
            "quality_score",
            "growth_score",
            "momentum_score",
            "liquidity_score",
            "size_score",
            "risk_score",
            "risk_label",
            "overall_score",
            "overall_label",
            "score_confidence",
        ]
        return self._simple_table(["Nhóm điểm", "Giá trị"], [(key, self._value(scores.get(key))) for key in display_keys])

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
                    self._text(item.get("published_at"), "Chưa có dữ liệu"),
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

    def _peer_comparison_section(self, summary: dict[str, Any]) -> str:
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
        table = self._simple_table(["Yếu tố", "Dữ liệu Backend"], [(name, self._value(value)) for name, value in rows])
        return f"{table}\n\nCần kiểm tra thêm chất lượng lợi nhuận, dòng tiền và thuyết minh BCTC nếu Backend chưa cung cấp đủ dữ liệu."

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
            "Đối chiếu giá, volume, EPS, P/E, P/B, ROE với nguồn Backend hoặc nguồn dữ liệu gốc.",
            "Mở các URL tin tức/nghiên cứu bên ngoài để xác nhận tiêu đề, ngày đăng và nội dung.",
            "Kiểm tra BCTC, dòng tiền, nợ vay và thuyết minh nếu dữ liệu Backend chưa đầy đủ.",
            "Xác định mức vốn, mức rủi ro mỗi giao dịch và tỷ trọng tối đa trước khi đặt lệnh.",
            "Không xem báo cáo này là khuyến nghị đầu tư cá nhân hóa.",
        ]
        if not research.get("items"):
            items.append("External research đang trống; cần kiểm tra thêm tin tức mới nhất bằng nguồn độc lập.")
        return "\n".join(f"- [ ] {item}" for item in items)

    def _metric_dictionary(self) -> str:
        return self._simple_table(
            ["Chỉ số", "Cách đọc"],
            [
                ("Giá đóng cửa", "Giá giao dịch cuối kỳ/phiên do Backend cung cấp."),
                ("Volume", "Khối lượng giao dịch; dùng để kiểm tra thanh khoản và độ tin cậy của biến động giá."),
                ("EPS", "Lợi nhuận trên mỗi cổ phiếu; cần đối chiếu kỳ tính và nguồn dữ liệu."),
                ("P/E", "Giá trên lợi nhuận; thấp/cao cần so với ngành và chất lượng lợi nhuận."),
                ("P/B", "Giá trên giá trị sổ sách; cần đọc cùng ROE và đặc thù ngành."),
                ("ROE", "Lợi nhuận trên vốn chủ sở hữu; phản ánh hiệu quả sử dụng vốn nếu dữ liệu đáng tin cậy."),
                ("Momentum", "Biến động giá trong chuỗi chart Backend trả về, không phải dự báo chắc chắn."),
                ("Tone tin tức", "Phân loại keyword đơn giản: tích cực, tiêu cực, hỗn hợp hoặc trung tính."),
            ],
        )

    def _dict_table(self, data: dict[str, Any], empty_text: str = "Chưa có dữ liệu") -> str:
        if not data:
            return empty_text
        return self._simple_table(["Trường", "Giá trị"], [(key, self._value(value)) for key, value in data.items()])

    def _simple_table(self, headers: list[str], rows: list[tuple[Any, ...]]) -> str:
        if not rows:
            return "Chưa có dữ liệu"
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
            return f"{prefix}Chưa có dữ liệu"
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
            return "Chưa có dữ liệu"
        if isinstance(value, bool):
            return "Có" if value else "Không"
        if isinstance(value, (int, float)):
            return f"{value:,}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"
        if isinstance(value, list):
            if not value:
                return "Chưa có dữ liệu"
            return "; ".join(self._value(item) for item in value)
        if isinstance(value, dict):
            if not value:
                return "Chưa có dữ liệu"
            return "; ".join(f"{key}: {self._value(item)}" for key, item in value.items())
        return str(value)

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
