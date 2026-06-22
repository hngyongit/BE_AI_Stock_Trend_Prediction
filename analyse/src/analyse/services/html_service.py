from __future__ import annotations

import html
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from analyse.config.settings import Settings, get_settings
from analyse.schemas.common import DEFAULT_DISCLAIMER
from analyse.schemas.report import HtmlReport


class HtmlService:
    """Tạo HTML report hoàn chỉnh, không inject HTML thô từ dữ liệu động."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build(
        self,
        report_id: str,
        summary: dict[str, Any],
        markdown_content: str | None = None,
        data_sources: list[dict[str, Any]] | None = None,
        provider: dict[str, Any] | None = None,
    ) -> str:
        symbol = self._text(summary.get("symbol"), "UNKNOWN")
        exchange = self._text(summary.get("scope_exchange"), "HOSE")
        company = self._text(summary.get("company"), "Chưa rõ tên công ty")
        decision = self._dict(summary.get("system_decision"))
        disclaimer = self._text(summary.get("disclaimer"), DEFAULT_DISCLAIMER)
        title = f"Báo cáo phân tích cổ phiếu {symbol} trên {exchange}"

        sections = [
            self._cover_section(title, symbol, exchange, company, decision, disclaimer),
            self._executive_summary(summary),
            self._market_context(summary),
            self._stock_quality_dashboard(summary),
            self._financial_statement_analysis(summary),
            self._peer_comparison(summary),
            self._external_research(summary),
            self._investment_memo(summary),
            self._action_plan(summary),
            self._strengths(summary),
            self._weaknesses_risks(summary),
            self._scenario_matrix(summary),
            self._checklist(summary),
            self._metric_dictionary(),
            self._data_coverage(summary, data_sources=data_sources, provider=provider),
            self._appendix(markdown_content),
        ]
        return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{self._e(title)}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --paper: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --brand: #0f766e;
      --brand-2: #1d4ed8;
      --warn: #b45309;
      --risk: #b91c1c;
      --good: #047857;
      --soft: #eef7f5;
      --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.55;
    }}
    a {{ color: var(--brand-2); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 24px;
      color: #fff;
      background: #111827;
      border-bottom: 1px solid rgba(255,255,255,0.12);
    }}
    .topbar strong {{ display: block; font-size: 14px; }}
    .topbar span {{ color: #cbd5e1; font-size: 12px; }}
    .layout {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: calc(100vh - 54px);
    }}
    .sidebar {{
      position: sticky;
      top: 54px;
      height: calc(100vh - 54px);
      overflow: auto;
      padding: 24px 18px;
      background: #fff;
      border-right: 1px solid var(--line);
    }}
    .sidebar a {{
      display: block;
      padding: 8px 10px;
      border-radius: 6px;
      color: #334155;
      font-size: 13px;
    }}
    .sidebar a:hover {{ background: var(--soft); text-decoration: none; }}
    main {{ padding: 28px; max-width: 1180px; width: 100%; }}
    section {{
      margin-bottom: 22px;
      padding: 24px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    #cover {{
      padding: 34px;
      background: linear-gradient(135deg, #ffffff 0%, #eef7f5 55%, #eff6ff 100%);
    }}
    h1, h2, h3 {{ margin: 0 0 12px; line-height: 1.2; letter-spacing: 0; }}
    h1 {{ font-size: 34px; }}
    h2 {{ font-size: 22px; }}
    h3 {{ font-size: 16px; color: #334155; }}
    p {{ margin: 0 0 12px; }}
    .muted {{ color: var(--muted); }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 5px 8px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
      color: #334155;
      font-size: 12px;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .kpi {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .kpi span {{ display: block; color: var(--muted); font-size: 12px; }}
    .kpi strong {{ display: block; margin-top: 4px; font-size: 20px; overflow-wrap: anywhere; }}
    .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
    th {{ color: #475569; background: #f8fafc; font-weight: 700; }}
    .news-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .news-card {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .news-card h3 {{ margin-bottom: 6px; }}
    .tone-tích-cực {{ color: var(--good); }}
    .tone-tiêu-cực {{ color: var(--risk); }}
    .tone-hỗn-hợp {{ color: var(--warn); }}
    ul {{ margin: 8px 0 0; padding-left: 20px; }}
    pre {{
      max-height: 680px;
      overflow: auto;
      padding: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      background: #0f172a;
      color: #e5e7eb;
      border-radius: 8px;
      font-size: 12px;
    }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: relative; top: 0; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
      main {{ padding: 16px; }}
      .kpis, .grid-2, .news-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 28px; }}
      .topbar {{ position: relative; flex-direction: column; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .topbar, .sidebar {{ display: none; }}
      .layout {{ display: block; }}
      main {{ max-width: none; padding: 0; }}
      section {{ box-shadow: none; border: 1px solid #d0d7de; break-inside: avoid; }}
      a {{ color: #000; text-decoration: underline; }}
      pre {{ max-height: none; color: #111; background: #f6f8fa; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div><strong>{self._e(symbol)} / {self._e(exchange)}</strong><span>{self._e(company)}</span></div>
    <div><strong>{self._e(self._text(decision.get("status"), "Chưa có dữ liệu"))}</strong><span>{self._e(report_id)}</span></div>
  </header>
  <div class="layout">
    <nav class="sidebar" aria-label="Mục lục">
      {self._toc()}
    </nav>
    <main>
      {''.join(sections)}
    </main>
  </div>
</body>
</html>
"""

    def build_metadata(self, report_id: str, summary: dict[str, Any]) -> HtmlReport:
        output_path = Path(self.settings.report_output_dir) / f"{report_id}.html"
        return HtmlReport(
            available=True,
            output_path=str(output_path).replace("\\", "/"),
            content=None,
            template_name="HtmlService.build",
        )

    def _toc(self) -> str:
        items = [
            ("cover", "Trang bìa"),
            ("executive-summary", "Kết luận"),
            ("market-context", "Bối cảnh thị trường"),
            ("stock-quality-dashboard", "Dashboard chỉ số"),
            ("financial-statement-analysis", "BCTC"),
            ("peer-comparison", "Peer cùng ngành"),
            ("external-research", "Tin tức/nghiên cứu"),
            ("investment-memo", "Investment memo"),
            ("action-plan", "Kế hoạch hành động"),
            ("strengths", "Điểm mạnh"),
            ("weaknesses-risks", "Rủi ro"),
            ("scenario-matrix", "Kịch bản"),
            ("checklist", "Checklist"),
            ("metric-dictionary", "Từ điển chỉ số"),
            ("data-coverage", "Độ phủ dữ liệu"),
            ("appendix", "Appendix Markdown"),
        ]
        return "\n".join(f'<a href="#{item_id}">{self._e(label)}</a>' for item_id, label in items)

    def _cover_section(self, title: str, symbol: str, exchange: str, company: str, decision: dict[str, Any], disclaimer: str) -> str:
        return f"""
<section id="cover">
  <h1>{self._e(title)}</h1>
  <p class="muted">{self._e(company)}</p>
  <div class="badge-row">
    <span class="badge">Mã: {self._e(symbol)}</span>
    <span class="badge">Sàn: {self._e(exchange)}</span>
    <span class="badge">Trạng thái: {self._e(self._text(decision.get("status"), "Chưa có dữ liệu"))}</span>
  </div>
  <p style="margin-top:18px">{self._e(disclaimer)}</p>
</section>
"""

    def _executive_summary(self, summary: dict[str, Any]) -> str:
        decision = self._dict(summary.get("system_decision"))
        return f"""
<section id="executive-summary">
  <h2>Kết luận hệ thống</h2>
  <div class="grid-2">
    <div>{self._field_table({"Trạng thái": decision.get("status"), "Hành động": decision.get("action"), "Ghi chú": decision.get("note")})}</div>
    <div><h3>Lý do</h3>{self._list(decision.get("reasons"))}</div>
  </div>
</section>
"""

    def _market_context(self, summary: dict[str, Any]) -> str:
        context = self._dict(summary.get("market_general_context")) or self._dict(summary.get("hose_market_context"))
        return f"""
<section id="market-context">
  <h2>Bối cảnh VNINDEX/HoSE</h2>
  {self._field_table(context) if context else '<p>Chưa có dữ liệu</p>'}
</section>
"""

    def _stock_quality_dashboard(self, summary: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        financial = self._dict(summary.get("financial_balance"))
        momentum = self._dict(summary.get("momentum"))
        scores = self._dict(summary.get("scores"))
        cards = [
            ("Giá", self._first_value(latest, "close_price", "close", "last_price", "price")),
            ("Volume", self._first_value(latest, "volume", "total_volume", "trading_volume")),
            ("EPS", self._first_value(latest, "eps") or self._first_value(financial, "eps")),
            ("P/E", self._first_value(latest, "pe", "pe_ratio") or self._first_value(financial, "pe", "pe_ratio")),
            ("P/B", self._first_value(latest, "pb", "pb_ratio") or self._first_value(financial, "pb", "pb_ratio")),
            ("ROE", self._first_value(latest, "roe") or self._first_value(financial, "roe")),
            ("Momentum", scores.get("momentum_score") if scores else momentum.get("change_pct")),
            ("Điểm tổng", scores.get("overall_score")),
        ]
        score_table = self._field_table(self._display_scores(scores))
        explanations = summary.get("score_explanations") or scores.get("score_explanations")
        return f"""
<section id="stock-quality-dashboard">
  <h2>Stock Quality Dashboard</h2>
  <div class="kpis">{''.join(self._kpi(label, value) for label, value in cards)}</div>
  <h3 style="margin-top:16px">Bảng điểm</h3>
  {score_table}
  <h3 style="margin-top:16px">Giải thích scoring</h3>
  {self._list(explanations)}
</section>
"""

    def _financial_statement_analysis(self, summary: dict[str, Any]) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        financial = self._dict(summary.get("financial_balance"))
        periods = bctc.get("periods")
        if isinstance(periods, list) and periods:
            table = self._list_of_dicts_table(
                periods,
                preferred_keys=[
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
                ],
            )
            if financial:
                table += f"<h3 style=\"margin-top:16px\">Financial balance</h3>{self._field_table(financial)}"
        elif financial:
            table = self._field_table(financial)
        else:
            table = f"<p>{self._e(self._value(bctc.get('data_quality_notes')))}</p>"
        return f"""
<section id="financial-statement-analysis">
  <h2>Phân tích BCTT kỳ chọn</h2>
  {table}
</section>
"""

    def _peer_comparison(self, summary: dict[str, Any]) -> str:
        peer = self._dict(summary.get("industry_peer_context"))
        same = self._dict(summary.get("same_industry_recommendation"))
        industry = self._dict(peer.get("industry"))
        peers = peer.get("peers") if isinstance(peer.get("peers"), list) else []
        candidates = same.get("candidates") if isinstance(same.get("candidates"), list) else []
        return f"""
<section id="peer-comparison">
  <h2>So sánh peer cùng ngành</h2>
  <h3>Ngành</h3>
  {self._field_table(industry) if industry else '<p>Chưa có dữ liệu</p>'}
  <h3 style="margin-top:16px">Peer table</h3>
  {self._list_of_dicts_table(peers, preferred_keys=["symbol", "company", "exchange", "close_price", "pe", "pb", "roe", "market_cap", "profit_after_tax", "revenue", "momentum_1m"]) if peers else '<p>Chưa có dữ liệu</p>'}
  <h3 style="margin-top:16px">Same industry candidates</h3>
  {self._list_of_dicts_table(candidates, preferred_keys=["symbol", "company", "close_price", "pe", "pb", "roe", "market_cap", "momentum_1m"]) if candidates else self._field_table(same) if same else '<p>Chưa có dữ liệu</p>'}
</section>
"""

    def _external_research(self, summary: dict[str, Any]) -> str:
        context = self._dict(summary.get("external_research_context"))
        items = context.get("items") if isinstance(context.get("items"), list) else []
        cards = "".join(self._news_card(item) for item in items if isinstance(item, dict))
        source_statuses = context.get("source_statuses") if isinstance(context.get("source_statuses"), list) else []
        return f"""
<section id="external-research">
  <h2>Nghiên cứu tin tức/ngành/thị trường bên ngoài</h2>
  <p class="muted">{self._e(self._text(context.get("note"), "Tin tức bên ngoài chỉ là bằng chứng ngữ cảnh; cần kiểm chứng URL gốc."))}</p>
  <div class="news-grid">{cards if cards else '<p>Chưa có dữ liệu</p>'}</div>
  <h3 style="margin-top:16px">Trạng thái nguồn</h3>
  {self._list_of_dicts_table(source_statuses) if source_statuses else '<p>Chưa có dữ liệu</p>'}
</section>
"""

    def _investment_memo(self, summary: dict[str, Any]) -> str:
        decision = self._dict(summary.get("system_decision"))
        return f"""
<section id="investment-memo">
  <h2>Investment memo</h2>
  {self._field_table({"Luận điểm": decision.get("action"), "Trạng thái": decision.get("status"), "Rủi ro dữ liệu": summary.get("data_quality_notes")})}
</section>
"""

    def _action_plan(self, summary: dict[str, Any]) -> str:
        plan = self._dict(summary.get("investment_plan"))
        action_table = plan.get("action_table")
        return f"""
<section id="action-plan">
  <h2>Kế hoạch hành động</h2>
  <div class="grid-2">
    <div><h3>Vào vị thế 4-5 tuần</h3>{self._list_of_dicts_table(action_table) if isinstance(action_table, list) and action_table else '<p>Cần kiểm tra thêm</p>'}</div>
    <div><h3>Quản trị vốn</h3>{self._field_table(self._dict(plan.get("position_sizing")))}</div>
  </div>
</section>
"""

    def _strengths(self, summary: dict[str, Any]) -> str:
        return f"""
<section id="strengths">
  <h2>Điểm mạnh cụ thể</h2>
  {self._list(summary.get("strengths"))}
</section>
"""

    def _weaknesses_risks(self, summary: dict[str, Any]) -> str:
        return f"""
<section id="weaknesses-risks">
  <h2>Điểm yếu và rủi ro cụ thể</h2>
  {self._list(summary.get("weaknesses"))}
</section>
"""

    def _scenario_matrix(self, summary: dict[str, Any]) -> str:
        scenario = summary.get("scenario_matrix")
        if isinstance(scenario, list) and scenario:
            content = self._list_of_dicts_table(scenario)
        else:
            content = self._table(
                ["Kịch bản", "Điều kiện cần kiểm tra", "Ứng xử tham khảo"],
                [
                    ("Tích cực", "Giá, thanh khoản, kết quả kinh doanh và tin tức xác nhận cùng chiều.", "Cần kiểm tra thêm trước khi tăng tỷ trọng."),
                    ("Cơ sở", "Dữ liệu chưa đủ xác nhận xu hướng mạnh.", "Theo dõi và giữ kỷ luật quản trị vốn."),
                    ("Tiêu cực", "Tin xấu, suy giảm lợi nhuận, thanh khoản yếu hoặc thị trường chung xấu đi.", "Giảm rủi ro theo kế hoạch."),
                ],
            )
        return f"""
<section id="scenario-matrix">
  <h2>Ma trận kịch bản</h2>
  {content}
</section>
"""

    def _checklist(self, summary: dict[str, Any]) -> str:
        items = [
            "Đối chiếu giá, volume, EPS, P/E, P/B, ROE với nguồn dữ liệu gốc.",
            "Mở URL tin tức để xác nhận nội dung và ngày đăng.",
            "Kiểm tra BCTC, dòng tiền, nợ vay và thuyết minh nếu Backend chưa đủ dữ liệu.",
            "Xác định vốn, rủi ro mỗi giao dịch và tỷ trọng tối đa.",
            "Không xem báo cáo này là khuyến nghị đầu tư cá nhân hóa.",
        ]
        return f"""
<section id="checklist">
  <h2>Checklist trước khi đặt lệnh</h2>
  <ul>{''.join(f'<li>{self._e(item)}</li>' for item in items)}</ul>
</section>
"""

    def _metric_dictionary(self) -> str:
        rows = [
            ("Giá đóng cửa", "Giá giao dịch cuối kỳ/phiên do Backend cung cấp."),
            ("Volume", "Khối lượng giao dịch để kiểm tra thanh khoản."),
            ("EPS", "Lợi nhuận trên mỗi cổ phiếu; cần đối chiếu kỳ tính."),
            ("P/E", "Giá trên lợi nhuận; nên so với ngành và chất lượng lợi nhuận."),
            ("P/B", "Giá trên giá trị sổ sách; đọc cùng ROE và đặc thù ngành."),
            ("ROE", "Hiệu quả sử dụng vốn chủ sở hữu nếu dữ liệu đáng tin cậy."),
            ("Tone", "Phân loại keyword đơn giản từ tiêu đề/trích yếu tin tức."),
        ]
        return f"""
<section id="metric-dictionary">
  <h2>Từ điển chỉ số</h2>
  {self._table(["Chỉ số", "Cách đọc"], rows)}
</section>
"""

    def _data_coverage(
        self,
        summary: dict[str, Any],
        data_sources: list[dict[str, Any]] | None = None,
        provider: dict[str, Any] | None = None,
    ) -> str:
        provider_block = self._field_table(provider or {}) if provider else "<p>Chưa có dữ liệu</p>"
        sources_block = self._list_of_dicts_table(data_sources) if data_sources else "<p>Chưa có dữ liệu</p>"
        return f"""
<section id="data-coverage">
  <h2>Dữ liệu đầu vào và độ phủ</h2>
  {self._field_table(self._dict(summary.get("data_coverage")))}
  <h3 style="margin-top:16px">Data quality</h3>
  {self._field_table(self._dict(summary.get("data_quality")))}
  <h3 style="margin-top:16px">Cảnh báo/ghi chú</h3>
  {self._list(summary.get("data_quality_notes") or summary.get("warnings"))}
  <h3 style="margin-top:16px">Provider</h3>
  {provider_block}
  <h3 style="margin-top:16px">Nguồn dữ liệu</h3>
  {sources_block}
</section>
"""

    def _appendix(self, markdown_content: str | None) -> str:
        content = markdown_content or "Chưa có dữ liệu Markdown."
        return f"""
<section id="appendix">
  <h2>Appendix: toàn bộ Markdown report</h2>
  <pre>{self._e(content)}</pre>
</section>
"""

    def _kpi(self, label: str, value: Any) -> str:
        return f'<div class="kpi"><span>{self._e(label)}</span><strong>{self._e(self._value(value))}</strong></div>'

    def _news_card(self, item: dict[str, Any]) -> str:
        title = self._text(item.get("title"), "Chưa có tiêu đề")
        url = self._safe_url(item.get("url"))
        tone = self._text(item.get("tone"), "trung tính")
        flags = []
        flags.extend(item.get("positive_flags") or [])
        flags.extend(item.get("negative_flags") or [])
        flags.extend(item.get("catalyst_flags") or [])
        tone_class = "tone-" + tone.replace(" ", "-").lower()
        return f"""
<article class="news-card">
  <h3><a href="{self._e(url)}" target="_blank" rel="noopener noreferrer">{self._e(title)}</a></h3>
  <p class="muted">{self._e(self._text(item.get("source"), "Chưa rõ nguồn"))} · {self._e(self._text(item.get("published_at"), "Chưa có ngày"))}</p>
  <p class="{self._e(tone_class)}">Tone: {self._e(tone)}</p>
  <p>{self._e(self._text(item.get("snippet"), "Chưa có trích yếu"))}</p>
  <p class="muted">Flags: {self._e(", ".join(flags) if flags else "Chưa có dữ liệu")}</p>
</article>
"""

    def _field_table(self, data: dict[str, Any]) -> str:
        if not data:
            return "<p>Chưa có dữ liệu</p>"
        return self._table(["Trường", "Giá trị"], [(key, self._value(value)) for key, value in data.items()])

    def _list_of_dicts_table(self, rows: Any, preferred_keys: list[str] | None = None) -> str:
        if not isinstance(rows, list) or not rows:
            return "<p>Chưa có dữ liệu</p>"
        keys: list[str] = []
        for key in preferred_keys or []:
            if any(isinstance(row, dict) and key in row for row in rows):
                keys.append(key)
        for row in rows:
            if isinstance(row, dict):
                for key in row.keys():
                    if key not in keys:
                        keys.append(key)
        keys = keys[:8]
        body = []
        for row in rows[:8]:
            if isinstance(row, dict):
                body.append(tuple(self._value(row.get(key)) for key in keys))
        return self._table(keys, body) if keys and body else "<p>Chưa có dữ liệu</p>"

    def _display_scores(self, scores: dict[str, Any]) -> dict[str, Any]:
        keys = [
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
        return {key: scores.get(key) for key in keys if key in scores}

    def _table(self, headers: list[str], rows: list[tuple[Any, ...]]) -> str:
        if not headers or not rows:
            return "<p>Chưa có dữ liệu</p>"
        head = "".join(f"<th>{self._e(header)}</th>" for header in headers)
        body_rows = []
        for row in rows:
            padded = list(row) + [""] * max(len(headers) - len(row), 0)
            cells = "".join(f"<td>{self._e(self._value(value))}</td>" for value in padded[: len(headers)])
            body_rows.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"

    def _list(self, values: Any) -> str:
        items = []
        if isinstance(values, list):
            items = [self._value(item) for item in values if self._value(item) != "Chưa có dữ liệu"]
        elif isinstance(values, str) and values.strip():
            items = [values.strip()]
        if not items:
            return "<p>Chưa có dữ liệu</p>"
        return "<ul>" + "".join(f"<li>{self._e(item)}</li>" for item in items) + "</ul>"

    def _first_value(self, data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    def _safe_url(self, value: Any) -> str:
        raw = str(value or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            return raw
        return "#"

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

    def _text(self, value: Any, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _e(self, value: Any) -> str:
        return html.escape(str(value), quote=True)
