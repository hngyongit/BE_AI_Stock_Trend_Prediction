from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import urlparse

from analyse.config.settings import Settings, get_settings
from analyse.schemas.common import DEFAULT_DISCLAIMER
from analyse.schemas.report import HtmlReport
from analyse.services.presentation_contract import normalize_percent_score
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.services.presentation_contract import source_status_label
from analyse.services.presentation_contract import to_user_facing_source_name
from analyse.services.stock_data_service import StockDataService
from analyse.utils.datetime_utils import format_datetime_vi
from analyse.utils.datetime_utils import format_percent_ratio


def normalize_market_health_score(raw_score: Any, score_direction: str = "higher_is_better") -> int | None:
    if raw_score in (None, ""):
        return None
    if isinstance(raw_score, bool):
        return None
    if isinstance(raw_score, (int, float)):
        numeric = float(raw_score)
    else:
        text = str(raw_score).strip()
        if not text or "chưa xác minh" in text.lower():
            return None
        text = text.replace("%", "").replace(" ", "")
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            numeric = float(text)
        except ValueError:
            return None
    if numeric != numeric:
        return None
    if 0 <= numeric <= 1:
        numeric *= 100
    direction = str(score_direction or "higher_is_better").strip().lower()
    if direction in {"higher_is_risk", "higher_is_worse", "higher_is_bad", "risk", "riskier_is_higher"}:
        numeric = 100 - numeric
    return max(0, min(100, int(round(numeric))))


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
        presentation = self._presentation(summary)
        disclaimer = self._text(summary.get("disclaimer"), DEFAULT_DISCLAIMER)
        title = f"Báo cáo phân tích cổ phiếu {symbol} trên {exchange}"
        chart_runtime = self._build_chart_runtime(summary)
        self._save_chart_debug_artifacts(symbol, chart_runtime)

        sections = [
            self._cover_section(title, symbol, exchange, company, decision, disclaimer, report_id, provider, presentation),
            self._summary_strip(summary, presentation),
            self._executive_summary(summary, presentation),
            self._business_overview(summary, presentation),
            self._market_context(summary, presentation, chart_runtime),
            self._stock_quality_dashboard(summary, presentation, chart_runtime),
            self._financial_statement_analysis(summary, presentation, chart_runtime),
            self._valuation(summary, presentation),
            self._peer_comparison(summary, presentation, chart_runtime),
            self._external_research(summary, presentation),
            self._investment_memo(summary, presentation),
            self._action_plan(summary, presentation),
            self._strengths(summary),
            self._weaknesses_risks(summary, presentation),
            self._scenario_matrix(summary),
            self._checklist(summary),
            self._metric_dictionary(),
            self._data_coverage(summary, data_sources=data_sources, provider=provider, presentation=presentation),
        ]
        chart_asset_head = self._chart_asset_head(chart_runtime)
        chart_scripts = self._chart_scripts(chart_runtime)
        html_document = f"""<!doctype html>
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
      --brand: #0f4c5c;
      --brand-2: #1d4ed8;
      --warn: #b45309;
      --risk: #b91c1c;
      --good: #047857;
      --soft: #eef7f5;
      --amber-soft: #fff7ed;
      --blue-soft: #eff6ff;
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
      background: #0b1220;
      border-bottom: 1px solid rgba(255,255,255,0.12);
    }}
    .topbar strong {{ display: block; font-size: 14px; }}
    .topbar span {{ color: #cbd5e1; font-size: 12px; }}
    .layout {{
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
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
    main {{ padding: 28px; max-width: none; width: 100%; min-width: 0; }}
    section {{
      margin-bottom: 22px;
      padding: 24px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    #cover {{
      padding: 34px;
      background: linear-gradient(135deg, #ffffff 0%, #eef7f5 52%, #eff6ff 100%);
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
    .summary-strip {{
      position: sticky;
      top: 54px;
      z-index: 12;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
      margin-bottom: 22px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,0.95);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
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
    .score-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }}
    .score-card {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .score-card header {{ display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }}
    .score-number {{ font-size: 28px; font-weight: 800; }}
    .score-meter {{ height: 8px; border-radius: 999px; background: #e5e7eb; overflow: hidden; margin: 10px 0; }}
    .score-meter span {{ display: block; height: 100%; background: linear-gradient(90deg, var(--brand-2), var(--good)); }}
    .chart-panel {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      min-height: 180px;
      min-width: 0;
      overflow: hidden;
    }}
    .chart-panel h3 {{ overflow-wrap: normal; word-break: normal; hyphens: none; }}
    .chart-panel svg {{ display: block; width: 100%; height: 180px; }}
    .chart-axis {{ stroke: #e5e7eb; stroke-width: 1; }}
    .chart-line {{ fill: none; stroke: var(--brand-2); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }}
    .chart-area {{ fill: rgba(29, 78, 216, 0.10); }}
    .bar-row {{ display: grid; grid-template-columns: 150px minmax(0, 1fr) 58px; gap: 10px; align-items: center; margin: 8px 0; }}
    .bar-track {{ height: 10px; overflow: hidden; border-radius: 999px; background: #e5e7eb; }}
    .bar-fill {{ display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--brand-2), var(--good)); }}
    .market-cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }}
    .market-health-card {{
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
    }}
    .market-health-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }}
    .market-health-head h3 {{
      margin: 0 0 4px;
      font-size: 17px;
      line-height: 1.35;
    }}
    .market-health-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .market-health-score {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .market-health-score strong {{
      font-size: 28px;
      line-height: 1;
    }}
    .market-health-score span {{ color: var(--muted); }}
    .market-health-track {{
      position: relative;
      display: grid;
      grid-template-columns: 4fr 2fr 4fr;
      height: 14px;
      border-radius: 999px;
      overflow: visible;
      background: #e5e7eb;
    }}
    .market-health-track .zone {{ display: block; min-width: 0; height: 14px; }}
    .market-health-track .zone-risk {{ border-radius: 999px 0 0 999px; background: #fee2e2; }}
    .market-health-track .zone-neutral {{ background: #fef3c7; }}
    .market-health-track .zone-positive {{ border-radius: 0 999px 999px 0; background: #dcfce7; }}
    .market-health-track .marker {{
      position: absolute;
      top: -5px;
      width: 4px;
      height: 24px;
      border-radius: 999px;
      background: #0f172a;
      transform: translateX(-50%);
    }}
    .market-health-labels {{
      display: flex;
      justify-content: space-between;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .status-positive {{ background: #dcfce7; color: #166534; }}
    .status-neutral {{ background: #fef3c7; color: #92400e; }}
    .status-risk {{ background: #fee2e2; color: #991b1b; }}
    .table-scroll {{
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      overflow-y: visible;
      -webkit-overflow-scrolling: touch;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
    }}
    .table-scroll table {{ margin-top: 0; }}
    .financial-table {{
      min-width: 1280px;
      width: max-content;
      border-collapse: collapse;
    }}
    .financial-table th,
    .financial-table td {{
      white-space: nowrap;
      vertical-align: top;
    }}
    .financial-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f8fafc;
    }}
    .financial-charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
      margin-top: 16px;
    }}
    .chart-grid {{
      display: grid;
      gap: 16px;
      margin-top: 18px;
      min-width: 0;
    }}
    .chart-grid--two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .echart-card {{
      min-width: 0;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
    }}
    .chart-heading {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 8px;
    }}
    .chart-heading h3 {{
      margin: 0;
      font-size: 16px;
      color: #1f2937;
      overflow-wrap: normal;
      word-break: normal;
      hyphens: none;
    }}
    .chart-heading p {{ margin: 4px 0 0; color: var(--muted); font-size: 12px; }}
    .echart-box {{
      width: 100%;
      height: 320px;
      min-height: 280px;
    }}
    .echart-box--compact {{
      height: 280px;
      min-height: 260px;
    }}
    .chart-empty {{
      display: flex;
      min-height: 220px;
      align-items: center;
      justify-content: center;
      padding: 18px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      text-align: center;
      background: #f8fafc;
    }}
    .balance-health-card {{
      margin-top: 16px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .peer-card-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
    .peer-card {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .metric-explain {{
      margin: 10px 0 16px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8fafc;
    }}
    .metric-explain summary {{ cursor: pointer; font-weight: 700; }}
    .metric-explain p {{ margin: 10px 0 0; color: var(--muted); }}
    .coverage-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .coverage-card {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .source-list {{ display: grid; gap: 8px; }}
    .source-row {{ display: grid; grid-template-columns: minmax(160px, 1fr) auto minmax(180px, 1fr); align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .source-row small {{ color: var(--muted); line-height: 1.35; }}
    .timeline {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .timeline-card {{ padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--blue-soft); }}
    .timeline-card strong {{ display: block; margin-bottom: 4px; }}
    .roadmap {{ display: grid; gap: 10px; }}
    .roadmap-step {{ padding: 14px; border-left: 4px solid var(--brand-2); border-radius: 6px; background: var(--blue-soft); }}
    .pill {{ display: inline-flex; padding: 4px 8px; border-radius: 999px; background: var(--soft); color: var(--brand); font-size: 12px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
    th {{ color: #475569; background: #f8fafc; font-weight: 700; }}
    .news-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      align-items: stretch;
    }}
    .news-card {{
      min-height: 220px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 10px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .news-card h3 {{ margin-bottom: 6px; }}
    .news-card__title {{
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      min-height: 58px;
    }}
    .news-card__snippet {{
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .news-card__footer {{
      margin-top: auto;
      padding-top: 10px;
      border-top: 1px solid var(--line);
    }}
    .news-badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }}
    .research-group {{ margin-top: 18px; }}
    .callout {{ padding: 14px; border-radius: 8px; border: 1px solid #bae6fd; background: #f0f9ff; }}
    .right {{ text-align: right; }}
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
      .kpis, .summary-strip, .grid-2, .score-grid, .news-grid, .market-cards, .financial-charts-grid, .chart-grid--two, .timeline, .source-row {{ grid-template-columns: 1fr; position: relative; top: 0; }}
      h1 {{ font-size: 28px; }}
      .topbar {{ position: relative; flex-direction: column; }}
    }}
    @media (max-width: 1200px) {{
      .financial-charts-grid {{ grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
      .chart-grid--two {{ grid-template-columns: 1fr; }}
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
  {chart_asset_head}
</head>
<body>
  <header class="topbar">
    <div><strong>{self._e(symbol)} / {self._e(exchange)}</strong><span>{self._e(company)}</span></div>
    <div><strong>{self._e(self._text(decision.get("status"), "Chưa xác minh"))}</strong><span>{self._e(report_id)}</span></div>
  </header>
  <div class="layout">
    <nav class="sidebar" aria-label="Mục lục">
      {self._toc()}
    </nav>
    <main>
      {''.join(sections)}
    </main>
  </div>
  {chart_scripts}
</body>
</html>
"""
        self._save_html_layout_debug(symbol, html_document, summary)
        return self._sanitize_main_sections(html_document)

    def build_metadata(self, report_id: str, summary: dict[str, Any]) -> HtmlReport:
        output_path = Path(self.settings.report_output_dir) / f"{report_id}.html"
        return HtmlReport(
            available=True,
            output_path=str(output_path).replace("\\", "/"),
            content=None,
            template_name="HtmlService.build",
        )

    def _save_html_layout_debug(self, symbol: str, html_document: str, summary: dict[str, Any]) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            bctc = self._dict(summary.get("bctc_3q"))
            periods = bctc.get("periods") if isinstance(bctc.get("periods"), list) else []
            peer_context = self._dict(summary.get("industry_peer_context"))
            peers = peer_context.get("peers") if isinstance(peer_context.get("peers"), list) else []
            payload = {
                "symbol": symbol,
                "has_financial_grid": "financial-grid" in html_document,
                "has_table_scroll": "table-scroll" in html_document,
                "has_financial_charts_grid": "financial-charts-grid" in html_document,
                "has_echarts": "chart-data-report" in html_document and "echarts.init" in html_document,
                "financial_periods": [period.get("period") for period in periods if isinstance(period, dict)],
                "peer_count": len(peers),
                "section_ids": sorted(set(re.findall(r'<section id="([^"]+)"', html_document))),
            }
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{symbol}_html_layout_context.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _save_chart_debug_artifacts(self, symbol: str, chart_runtime: dict[str, Any]) -> None:
        if not (self.settings.external_data_debug_save_extraction_json or self.settings.vietstock_debug_save_extraction_json):
            return
        try:
            charts = chart_runtime.get("charts") if isinstance(chart_runtime.get("charts"), list) else []
            chart_ids = [chart.get("id") for chart in charts if isinstance(chart, dict) and chart.get("id")]
            asset = self._dict(chart_runtime.get("asset"))
            validation = {
                "valid_json_serializable": True,
                "valid_chart_ids": bool(all(isinstance(chart_id, str) and chart_id for chart_id in chart_ids)),
                "chart_count": len(charts),
            }
            try:
                json.dumps({"charts": charts}, ensure_ascii=False)
            except TypeError as exc:
                validation["valid_json_serializable"] = False
                validation["error"] = f"{exc.__class__.__name__}: {exc}"
            debug_dir = Path(self.settings.report_output_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{symbol}_chart_payload.json").write_text(
                json.dumps({"charts": charts, "chart_ids": chart_ids, "validation": validation}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            asset_payload = {
                "selected_chart_engine": chart_runtime.get("engine"),
                "requested_chart_engine": self._chart_engine_name(self.settings.report_chart_engine),
                "fallback_mode": chart_runtime.get("fallback_engine") or self._chart_engine_name(self.settings.report_chart_fallback),
                "local_asset_path": asset.get("local_asset_path"),
                "local_asset_exists": bool(asset.get("local_asset_exists")),
                "script_src_used_in_html": chart_runtime.get("script_src"),
                "chart_count": len(charts),
                "chart_ids": chart_ids,
                "chart_data_validation": validation,
                "reason_if_charts_not_rendered": chart_runtime.get("reason") or "",
                "warnings": chart_runtime.get("warnings") or [],
            }
            (debug_dir / f"{symbol}_chart_asset_check.json").write_text(
                json.dumps(asset_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    def _toc(self) -> str:
        items = [
            ("cover", "Trang bìa"),
            ("summary-strip", "Tổng quan nhanh"),
            ("executive-summary", "Kết luận"),
            ("business-overview", "Doanh nghiệp"),
            ("market-context", "Bối cảnh thị trường"),
            ("stock-quality-dashboard", "Dashboard chỉ số"),
            ("financial-statement-analysis", "BCTC"),
            ("valuation", "Định giá"),
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
        ]
        return "\n".join(f'<a href="#{item_id}">{self._e(label)}</a>' for item_id, label in items)

    def _presentation(self, summary: dict[str, Any]) -> dict[str, Any]:
        existing = self._dict(summary.get("report_presentation"))
        if existing:
            return existing
        scores = self._dict(summary.get("scores"))
        return {
            "executive_summary": {
                "status": self._dict(summary.get("system_decision")).get("status"),
                "main_thesis": self._dict(summary.get("system_decision")).get("action"),
                "key_positives": summary.get("strengths"),
                "key_risks": summary.get("weaknesses"),
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
            "data_quality": {"user_notes": summary.get("data_quality_notes"), "technical_notes": summary.get("technical_data_quality_notes")},
        }

    def _cover_section(
        self,
        title: str,
        symbol: str,
        exchange: str,
        company: str,
        decision: dict[str, Any],
        disclaimer: str,
        report_id: str,
        provider: dict[str, Any] | None,
        presentation: dict[str, Any],
    ) -> str:
        executive = self._dict(presentation.get("executive_summary"))
        scores = self._dict(presentation.get("summary_bar")) or self._dict({})
        provider_label = " / ".join(
            item for item in (self._text((provider or {}).get("name"), ""), self._text((provider or {}).get("model"), "")) if item
        ) or "Chưa xác minh"
        return f"""
<section id="cover">
  <h1>{self._e(title)}</h1>
  <p class="muted">{self._e(company)}</p>
  <div class="badge-row">
    <span class="badge">Mã: {self._e(symbol)}</span>
    <span class="badge">Sàn: {self._e(exchange)}</span>
    <span class="badge">Trạng thái: {self._e(self._text(executive.get("status") or decision.get("status"), "Chưa xác minh"))}</span>
    <span class="badge">Điểm tổng: {self._e(self._value(scores.get("overall_score")))}</span>
    <span class="badge">Tỷ lệ tin cậy: {self._e(self._format_confidence(scores.get("data_confidence")))}</span>
  </div>
  <p class="muted" style="margin-top:12px">Mã báo cáo: {self._e(report_id)} · Nguồn mô hình: {self._e(provider_label)}</p>
  <p style="margin-top:18px">{self._e(disclaimer)}</p>
</section>
"""

    def _summary_strip(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        bar = self._dict(presentation.get("summary_bar"))
        items = [
            ("Giá", bar.get("latest_price")),
            ("Biến động kỳ chart", bar.get("chart_return")),
            ("Điểm tổng", bar.get("overall_score")),
            ("Rủi ro", bar.get("risk_label")),
            ("Số kỳ BCTC", bar.get("financial_periods_count")),
            ("Tỷ lệ tin cậy dữ liệu", bar.get("data_confidence")),
        ]
        return f'<div id="summary-strip" class="summary-strip">{"".join(self._kpi(label, value) for label, value in items)}</div>'

    def _executive_summary(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        executive = self._dict(presentation.get("executive_summary"))
        return f"""
<section id="executive-summary">
  <h2>Tóm tắt điều hành</h2>
  <div class="grid-2">
    <div>{self._field_table({"Trạng thái": executive.get("status"), "Luận điểm chính": executive.get("main_thesis"), "Tỷ lệ tin cậy": f"{self._format_confidence(executive.get('confidence'))} ({self._text(executive.get('confidence_label'), 'Chưa xác minh')})"})}</div>
    <div><h3>Điều cần kiểm tra</h3>{self._list(executive.get("checks_before_action"))}</div>
  </div>
  <div class="grid-2" style="margin-top:14px">
    <div><h3>Điểm tích cực</h3>{self._list(executive.get("key_positives"))}</div>
    <div><h3>Rủi ro chính</h3>{self._list(executive.get("key_risks"))}</div>
  </div>
</section>
"""

    def _business_overview(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        overview = self._dict(presentation.get("business_overview"))
        industry = self._dict(overview.get("industry"))
        source = self._overview_source_value(overview, industry)
        leadership = self._list_dicts(overview.get("leadership"))
        ownership = self._list_dicts(overview.get("ownership"))
        group = industry.get("industry_level_2") or industry.get("industry_group") or industry.get("group")
        detail = industry.get("industry_level_3") or industry.get("industry") or industry.get("industry_name")
        profile_rows = [
            ("Doanh nghiệp", overview.get("company_name") or summary.get("company")),
            ("Sàn", overview.get("exchange") or summary.get("scope_exchange") or summary.get("exchange")),
            ("Nhóm ngành", group),
            ("Mô tả ngắn", overview.get("business_overview")),
            ("Nguồn", source),
        ]
        return f"""
<section id="business-overview">
  <h2>Tổng quan doanh nghiệp</h2>
  <p>{self._e(self._text(overview.get("description"), "Chưa đủ dữ liệu xác thực để mô tả mô hình kinh doanh."))}</p>
  {self._table(["Nội dung", "Giá trị"], profile_rows)}
  <h3 style="margin-top:16px">Ban lãnh đạo</h3>
  {self._leadership_table(leadership)}
  <h3 style="margin-top:16px">Sở hữu / cổ đông lớn</h3>
  {self._ownership_table(ownership)}
  <h3 style="margin-top:16px">Nhóm ngành tham chiếu</h3>
  {self._industry_reference_table(group, detail, source)}
  <h3 style="margin-top:16px">Bối cảnh cần theo dõi</h3>
  {self._list(overview.get("drivers"))}
</section>
"""

    def _market_context(self, summary: dict[str, Any], presentation: dict[str, Any], chart_runtime: dict[str, Any] | None = None) -> str:
        view = self._dict(presentation.get("market_context_view"))
        cards = self._list_dicts(view.get("cards"))
        card_html = "".join(self._kpi(card.get("label"), card.get("value")) for card in cards) if cards else ""
        market_chart_type = self._market_chart_type()
        if market_chart_type == "none":
            market_chart = ""
        elif market_chart_type == "echarts_bar" and self._use_echarts(chart_runtime):
            market_chart = self._echart_card("market-health-score", chart_runtime)
            if not market_chart:
                market_chart = self._market_health_card(summary, view)
        else:
            market_chart = self._market_health_card(summary, view)
        return f"""
<section id="market-context">
  <h2>Bối cảnh VNINDEX/HoSE</h2>
  <p>{self._e(self._text(view.get("narrative") or presentation.get("market_context"), "Bối cảnh thị trường cần được đối chiếu thêm."))}</p>
  <div class="market-cards">{card_html if card_html else '<p>Chưa đủ dữ liệu xác thực để đánh giá bối cảnh thị trường.</p>'}</div>
  {market_chart}
</section>
"""

    def _market_health_card(self, summary: dict[str, Any], view: dict[str, Any]) -> str:
        score = self._market_health_score(summary, view)
        label, status_class = self._market_health_status(score)
        if score is None:
            return f"""
  <div class="market-health-card">
    <div class="market-health-head">
      <div>
        <h3>Thước đo sức khỏe thị trường</h3>
        <p>0 là thận trọng hơn, 100 là tích cực hơn.</p>
      </div>
      <span class="status-badge status-neutral">Cần thêm dữ liệu</span>
    </div>
    <div class="chart-empty">Chưa đủ dữ liệu để dựng thước đo sức khỏe thị trường.</div>
  </div>
"""
        display_symbol = self._market_display_symbol(summary)
        explanation = f"{display_symbol} đang nghiêng {label.lower()} trong phiên dữ liệu gần nhất."
        return f"""
  <div class="market-health-card">
    <div class="market-health-head">
      <div>
        <h3>Thước đo sức khỏe thị trường</h3>
        <p>0 là thận trọng hơn, 100 là tích cực hơn.</p>
      </div>
      <span class="status-badge {status_class}">{self._e(label)}</span>
    </div>
    <div class="market-health-score">
      <strong>{score}/100</strong>
      <span>{self._e(explanation)}</span>
    </div>
    <div class="market-health-bar">
      <div class="market-health-track">
        <span class="zone zone-risk"></span>
        <span class="zone zone-neutral"></span>
        <span class="zone zone-positive"></span>
        <span class="marker" style="left:{score}%"></span>
      </div>
      <div class="market-health-labels">
        <span>Thận trọng</span>
        <span>Trung tính</span>
        <span>Tích cực</span>
      </div>
    </div>
    <p class="muted" style="margin-top:12px">Ngày cập nhật: {self._e(self._text(view.get("display_date"), "Chưa xác minh"))} · Nguồn: {self._e(self._text(view.get("source"), "Chưa xác minh"))}</p>
  </div>
"""

    def _market_chart_type(self) -> str:
        value = str(getattr(self.settings, "report_market_chart_type", "segmented_bar") or "segmented_bar").strip().lower()
        return value if value in {"segmented_bar", "echarts_bar", "none"} else "segmented_bar"

    def _market_health_score(self, summary: dict[str, Any], view: dict[str, Any]) -> int | None:
        market_general = self._dict(summary.get("market_general_context"))
        primary = self._dict(market_general.get("primary_index"))
        market = primary or self._dict(summary.get("hose_market_context")) or market_general
        raw_score = self._first_value(view, "market_health_score", "health_score", "regime_score", "regimeScore")
        if raw_score is None:
            raw_score = self._first_value(market, "market_health_score", "health_score", "regime_score", "regimeScore")
        direction = self._first_value(view, "score_direction", "regime_score_direction", "scoreDirection")
        if direction is None:
            direction = self._first_value(market, "score_direction", "regime_score_direction", "scoreDirection")
        if direction is None and market.get("regime_score_is_risk") is True:
            direction = "higher_is_risk"
        return normalize_market_health_score(raw_score, str(direction or "higher_is_better"))

    def _market_health_status(self, score: int | None) -> tuple[str, str]:
        if score is None:
            return "Cần thêm dữ liệu", "status-neutral"
        if score < 40:
            return "Thận trọng", "status-risk"
        if score < 60:
            return "Trung tính", "status-neutral"
        if score < 80:
            return "Tích cực", "status-positive"
        return "Rất tích cực", "status-positive"

    def _market_display_symbol(self, summary: dict[str, Any]) -> str:
        market_general = self._dict(summary.get("market_general_context"))
        primary = self._dict(market_general.get("primary_index"))
        market = primary or self._dict(summary.get("hose_market_context")) or market_general
        return self._text(market.get("display_symbol") or market.get("index_symbol"), "VN-Index")

    def _stock_quality_dashboard(self, summary: dict[str, Any], presentation: dict[str, Any], chart_runtime: dict[str, Any] | None = None) -> str:
        latest = self._dict(summary.get("latest_market"))
        financial = self._dict(summary.get("financial_balance"))
        momentum = self._dict(summary.get("momentum"))
        scores = self._dict(summary.get("scores"))
        cards = [
            ("Giá", self._first_value(latest, "close_price", "close", "last_price", "price")),
            ("Khối lượng", self._first_value(latest, "volume", "total_volume", "trading_volume")),
            ("EPS", self._first_value(latest, "eps") or self._first_value(financial, "eps", "eps_ttm")),
            ("P/E", self._first_value(latest, "pe", "pe_ratio") or self._first_value(financial, "pe", "pe_ratio")),
            ("P/B", self._first_value(latest, "pb", "pb_ratio") or self._first_value(financial, "pb", "pb_ratio")),
            ("ROE", self._first_value(latest, "roe") or self._first_value(financial, "roe")),
            ("Momentum", scores.get("momentum_score") if scores else momentum.get("change_pct")),
            ("Điểm tổng", scores.get("overall_score")),
        ]
        score_cards = presentation.get("score_cards")
        if isinstance(score_cards, list) and score_cards:
            score_block = '<div class="score-grid">' + ''.join(self._score_card(card) for card in score_cards if isinstance(card, dict)) + '</div>'
        else:
            score_block = self._field_table(self._display_scores(scores))
        explanations = summary.get("score_explanations") or scores.get("score_explanations")
        if self._use_echarts(chart_runtime):
            charts = f"""
  <div class="chart-grid chart-grid--two">
    {self._echart_card("score-dashboard", chart_runtime)}
    {self._echart_card("price-close-trend", chart_runtime) or self._price_momentum_chart(summary)}
  </div>
"""
        elif self._chart_engine(chart_runtime) == "none":
            charts = ""
        else:
            charts = f"""
  <div class="grid-2" style="margin-top:16px">
    {self._score_bar_chart(score_cards if isinstance(score_cards, list) else [])}
    {self._price_momentum_chart(summary)}
  </div>
"""
        return f"""
<section id="stock-quality-dashboard">
  <h2>Dashboard chất lượng cổ phiếu</h2>
  <div class="kpis">{''.join(self._kpi(label, value) for label, value in cards)}</div>
  {charts}
  <h3 style="margin-top:16px">Bảng điểm</h3>
  {score_block}
  <h3 style="margin-top:16px">Giải thích scoring</h3>
  {self._list(explanations)}
</section>
"""

    def _financial_statement_analysis(self, summary: dict[str, Any], presentation: dict[str, Any], chart_runtime: dict[str, Any] | None = None) -> str:
        bctc = self._dict(summary.get("bctc_3q"))
        financial = self._dict(summary.get("financial_balance"))
        periods = bctc.get("periods")
        commentary = self._text(presentation.get("financial_analysis"), "Bộ dữ liệu BCTC hiện chưa đủ để phân tích sâu.")
        if isinstance(periods, list) and periods:
            is_bank = self._has_bank_metrics(periods)
            table = self._wrap_table_scroll(
                self._with_table_class(self._financial_trend_table(periods), "data-table financial-table"),
                "financial-table-scroll",
            )
            balance = ""
            if financial:
                balance = (
                    '<div class="balance-health-card">'
                    '<h3>Sức khỏe bảng cân đối kỳ gần nhất</h3>'
                    f'{self._wrap_table_scroll(self._financial_balance_table(financial, is_bank=is_bank))}'
                    "</div>"
                )
            chart_block = (
                self._echart_grid(["financial-profit-trend", "financial-balance-scale", "financial-ratio-trend"], chart_runtime)
                if self._use_echarts(chart_runtime)
                else "" if self._chart_engine(chart_runtime) == "none" else self._financial_trend_chart(periods)
            )
            if self._use_echarts(chart_runtime) and not chart_block:
                chart_block = self._financial_trend_chart(periods)
            content = f"""
  {table}
  {chart_block}
  {balance}
"""
        elif financial:
            content = self._wrap_table_scroll(self._financial_balance_table(financial, is_bank=self._has_bank_metrics([financial])))
        else:
            content = (
                "<p>Chưa đủ dữ liệu xác thực để lập bảng tài chính định lượng. "
                "Báo cáo không suy diễn doanh thu, lợi nhuận hoặc bảng cân đối khi chưa có số liệu kiểm chứng.</p>"
            )
        return f"""
<section id="financial-statement-analysis">
  <h2>Phân tích tài chính</h2>
  <p>{self._e(commentary)}</p>
  {content}
</section>
"""

    def _valuation(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        latest = self._dict(summary.get("latest_market"))
        scores = self._dict(summary.get("scores"))
        rows = {
            "EPS": latest.get("eps"),
            "P/E": latest.get("pe"),
            "Forward P/E": latest.get("forward_pe"),
            "P/B": latest.get("pb"),
            "BVPS": latest.get("bvps"),
            "ROE": latest.get("roe"),
            "Điểm định giá": scores.get("valuation_score"),
        }
        return f"""
<section id="valuation">
  <h2>Định giá</h2>
  <p>{self._e(self._text(presentation.get("valuation"), "Chưa đủ dữ liệu định giá xác thực."))}</p>
  {self._field_table(rows)}
</section>
"""

    def _peer_comparison(self, summary: dict[str, Any], presentation: dict[str, Any], chart_runtime: dict[str, Any] | None = None) -> str:
        peer = self._dict(summary.get("industry_peer_context"))
        same = self._dict(summary.get("same_industry_recommendation"))
        industry = self._dict(peer.get("industry"))
        peers = peer.get("peers") if isinstance(peer.get("peers"), list) else []
        reference_candidates = presentation.get("reference_candidates")
        quantitative_peers = [item for item in peers if isinstance(item, dict) and self._has_peer_metrics(item)]
        qualitative_peers = [item for item in peers if isinstance(item, dict) and not self._has_peer_metrics(item)]
        peer_block = self._wrap_table_scroll(self._peer_table(quantitative_peers)) if quantitative_peers else (
            self._qualitative_peer_cards(qualitative_peers)
            if qualitative_peers
            else '<p>Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận.</p>'
        )
        peer_chart_block = (
            self._echart_grid(["peer-market-cap", "peer-pe-comparison", "peer-roe-comparison"], chart_runtime)
            if self._use_echarts(chart_runtime)
            else "" if self._chart_engine(chart_runtime) == "none" else self._peer_charts(quantitative_peers)
        )
        return f"""
<section id="peer-comparison">
  <h2>So sánh peer cùng ngành</h2>
  <p>{self._e(self._text(presentation.get("peer_note"), "Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận."))}</p>
  <p class="muted">Bảng này dùng để so sánh {self._e(self._text(summary.get("symbol"), "mã đang phân tích"))} với các doanh nghiệp cùng nhóm ngành. Các chỉ tiêu như vốn hóa, P/E, P/B, ROE và thanh khoản giúp đọc tương quan quy mô, định giá và hiệu quả sinh lời; đây là danh sách tham khảo để theo dõi, không phải khuyến nghị mua/bán cá nhân hóa.</p>
  {self._peer_metric_explain()}
  <h3>Ngành</h3>
  {self._industry_table(industry) if industry else '<p>Chưa đủ dữ liệu xác thực để xác định nhóm ngành.</p>'}
  <h3 style="margin-top:16px">Bảng peer định lượng</h3>
  {peer_block}
  {peer_chart_block if quantitative_peers else ''}
  <h3 style="margin-top:16px">Mã tham khảo cùng nhóm/ngành</h3>
  {self._reference_candidate_table(reference_candidates) if isinstance(reference_candidates, list) and reference_candidates else '<p>Chưa đủ dữ liệu xác thực để lập danh sách mã cùng ngành có thể so sánh định lượng.</p>'}
</section>
"""

    def _external_research(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        context = self._dict(summary.get("external_research_context"))
        insights = self._dict(presentation.get("research_insights"))
        raw_items = context.get("items") if isinstance(context.get("items"), list) else []
        if not any(isinstance(insights.get(key), list) and insights.get(key) for key in ("positive_catalysts", "risks", "background", "needs_verification")) and raw_items:
            insights = self._fallback_research_insights(raw_items)
        synthesis = self._text(insights.get("synthesis"), "Tin tức bên ngoài chỉ là bằng chứng ngữ cảnh; cần kiểm chứng URL gốc.")
        return f"""
<section id="external-research">
  <h2>Tin tức và dữ liệu bên ngoài</h2>
  <div class="callout">
    <p>{self._e(synthesis)}</p>
    <p class="muted">{self._e(self._text(context.get("note"), "Các mục dưới đây chỉ dùng làm bối cảnh; cần mở URL gốc để xác minh."))}</p>
  </div>
  {self._research_group("Catalyst tích cực", insights.get("positive_catalysts"))}
  {self._research_group("Rủi ro/tín hiệu cần thận trọng", insights.get("risks"))}
  {self._research_group("Bối cảnh ngành/thông tin nền", insights.get("background"))}
  {self._research_group("Cần kiểm chứng", insights.get("needs_verification"))}
</section>
"""

    def _fallback_research_insights(self, items: list[Any]) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {"positive_catalysts": [], "risks": [], "background": [], "needs_verification": []}
        for item in items:
            if not isinstance(item, dict):
                continue
            category = "risks" if item.get("negative_flags") else "positive_catalysts" if item.get("positive_flags") or item.get("catalyst_flags") else "background"
            snippet = self._text(item.get("snippet"), "")
            groups[category].append(
                {
                    "title": item.get("title"),
                    "source": self._source_display(item.get("source") or item.get("type")),
                    "url": item.get("url"),
                    "display_date": self._format_datetime(item.get("published_at")),
                    "tone": item.get("tone") or "trung tính",
                    "impact_horizon": "Bối cảnh",
                    "confidence_label": "Cần kiểm chứng",
                    "affected_factors": item.get("catalyst_flags") or item.get("positive_flags") or item.get("negative_flags") or ["Bối cảnh thông tin"],
                    "detailed_summary": (
                        f"Tiêu đề/trích yếu hiện có: {snippet}. "
                        "Báo cáo chỉ dùng thông tin này như bối cảnh và không suy diễn số liệu tài chính mới."
                        if snippet
                        else "Trong lần chạy này chỉ có tiêu đề, cần đọc nguồn gốc trước khi sử dụng trong luận điểm."
                    ),
                    "possible_impact": "Tác động định lượng chưa rõ, cần kiểm chứng bằng nguồn gốc và dữ liệu thị trường.",
                    "what_to_verify": "Mở URL gốc để kiểm tra ngày đăng, doanh nghiệp liên quan và số liệu trong bài.",
                }
            )
        total = sum(len(value) for value in groups.values())
        groups["synthesis"] = f"Có {total} mục tin tức/nghiên cứu được dùng làm bối cảnh; cần kiểm chứng URL gốc trước khi sử dụng." if total else "Chưa có đủ tin tức/nghiên cứu bên ngoài đã xác thực."
        return groups

    def _investment_memo(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        executive = self._dict(presentation.get("executive_summary"))
        return f"""
<section id="investment-memo">
  <h2>Investment memo</h2>
  {self._field_table({"Luận điểm": executive.get("main_thesis"), "Trạng thái": executive.get("status"), "Rủi ro dữ liệu": executive.get("key_risks"), "Điều cần kiểm tra": executive.get("checks_before_action")})}
</section>
"""

    def _action_plan(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        plan = self._dict(summary.get("investment_plan"))
        action_table = plan.get("action_table")
        roadmap = presentation.get("roadmap")
        return f"""
<section id="action-plan">
  <h2>Lộ trình theo dõi</h2>
  {self._roadmap_html(roadmap)}
  <div class="grid-2" style="margin-top:16px">
    <div>
      <h3>Tín hiệu có thể nâng chất lượng luận điểm</h3>
      {self._list(["Giá và thanh khoản xác nhận cùng chiều trong nhiều phiên.", "BCTC mới cho thấy doanh thu/lợi nhuận cải thiện có nguồn gốc rõ ràng.", "Tin tức/công bố chính thức củng cố catalyst đã nêu."])}
    </div>
    <div>
      <h3>Điều kiện cần thận trọng</h3>
      {self._list(["Thanh khoản suy yếu khi giá giảm.", "Bối cảnh thị trường chung chuyển sang phòng thủ.", "BCTC hoặc tin tức mới làm giảm độ tin cậy của luận điểm."])}
    </div>
  </div>
  <h3 style="margin-top:16px">Thông số quản trị vốn nếu người dùng cung cấp</h3>
  {self._position_sizing_table(self._dict(plan.get("position_sizing")))}
  {self._list_of_dicts_table(action_table) if isinstance(action_table, list) and action_table else ''}
</section>
"""

    def _strengths(self, summary: dict[str, Any]) -> str:
        return f"""
<section id="strengths">
  <h2>Điểm mạnh cụ thể</h2>
  {self._list(summary.get("strengths"))}
</section>
"""

    def _weaknesses_risks(self, summary: dict[str, Any], presentation: dict[str, Any]) -> str:
        executive = self._dict(presentation.get("executive_summary"))
        return f"""
<section id="weaknesses-risks">
  <h2>Điểm yếu và rủi ro cụ thể</h2>
  {self._list(executive.get("key_risks") or summary.get("weaknesses"))}
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
            "Kiểm tra BCTC, dòng tiền, nợ vay và thuyết minh nếu dữ liệu hiện có chưa đủ.",
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
            ("Giá đóng cửa", "Giá giao dịch cuối kỳ/phiên từ nguồn dữ liệu gốc."),
            ("Khối lượng", "Khối lượng giao dịch để kiểm tra thanh khoản."),
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
        presentation: dict[str, Any] | None = None,
    ) -> str:
        data_quality = self._dict((presentation or {}).get("data_quality"))
        user_notes = data_quality.get("user_notes") or summary.get("data_quality_notes")
        coverage_rows = (presentation or {}).get("coverage_rows")
        return f"""
<section id="data-coverage">
  <h2>Độ phủ dữ liệu và giới hạn</h2>
  <p>Phần này tóm tắt mức độ sẵn sàng của dữ liệu theo ngôn ngữ phân tích. Các chi tiết vận hành thô không được đưa vào bản báo cáo người dùng.</p>
  <h3>Ghi chú người đọc</h3>
  {self._list(user_notes)}
  {self._coverage_cards(coverage_rows)}
  <h3 style="margin-top:16px">Nguồn đã sử dụng</h3>
  {self._friendly_source_list(data_sources)}
</section>
"""

    def _kpi(self, label: str, value: Any) -> str:
        display = self._format_confidence(value) if "tin cậy" in label.lower() else self._value(value)
        return f'<div class="kpi"><span>{self._e(label)}</span><strong>{self._e(display)}</strong></div>'

    def _build_chart_runtime(self, summary: dict[str, Any]) -> dict[str, Any]:
        requested_engine = self._chart_engine_name(self.settings.report_chart_engine)
        fallback_engine = self._chart_engine_name(self.settings.report_chart_fallback)
        runtime: dict[str, Any] = {
            "engine": requested_engine,
            "script_src": None,
            "charts": [],
            "charts_by_id": {},
            "warnings": [],
            "asset": {},
            "fallback_engine": fallback_engine,
            "reason": "",
        }
        if requested_engine == "none":
            runtime["reason"] = "Chart engine is disabled."
            return runtime
        if requested_engine != "echarts":
            runtime["engine"] = requested_engine
            runtime["reason"] = f"Chart engine {requested_engine} uses static report charts."
            return runtime

        asset = self._prepare_echarts_asset()
        runtime["asset"] = asset
        if asset.get("script_src"):
            charts = self._build_chart_data_payload(summary)
            chart_ids = [chart.get("id") for chart in charts if isinstance(chart, dict) and chart.get("id")]
            runtime.update(
                {
                    "engine": "echarts",
                    "script_src": asset["script_src"],
                    "charts": charts,
                    "charts_by_id": {chart.get("id"): chart for chart in charts if isinstance(chart, dict) and chart.get("id")},
                    "warnings": asset.get("warnings") or [],
                    "chart_ids": chart_ids,
                    "reason": "" if charts else "No chart has at least two valid data points.",
                }
            )
            return runtime

        runtime["warnings"] = asset.get("warnings") or ["ECharts local asset not found; inline SVG fallback was used."]
        runtime["engine"] = fallback_engine if fallback_engine in {"inline_svg", "css_bars", "none"} else "inline_svg"
        runtime["reason"] = "ECharts asset was unavailable, so fallback chart mode was selected."
        return runtime

    def _chart_engine_name(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"echarts", "inline_svg", "css_bars", "none"} else "inline_svg"

    def _prepare_echarts_asset(self) -> dict[str, Any]:
        mode = str(self.settings.report_chart_asset_mode or "local").strip().lower()
        warnings: list[str] = []
        if mode == "cdn":
            if self.settings.report_chart_allow_cdn and self.settings.report_echarts_cdn_url:
                return {
                    "script_src": self.settings.report_echarts_cdn_url,
                    "warnings": warnings,
                    "asset_mode": "cdn",
                    "local_asset_path": None,
                    "local_asset_exists": False,
                }
            return {
                "script_src": None,
                "warnings": ["ECharts CDN is disabled; inline SVG fallback was used."],
                "asset_mode": "cdn",
                "local_asset_path": None,
                "local_asset_exists": False,
            }

        source = self._echarts_source_path()
        if not source.exists():
            return {
                "script_src": None,
                "warnings": ["ECharts local asset not found; inline SVG fallback was used."],
                "asset_mode": "local",
                "source_asset_path": str(source),
                "local_asset_path": str(self._chart_asset_dir_path() / source.name),
                "local_asset_exists": False,
            }

        asset_file_name = source.name or "echarts.min.js"
        asset_dir = self._chart_asset_dir_path()
        target = asset_dir / asset_file_name
        try:
            asset_dir.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        except Exception as exc:
            warnings.append(f"ECharts asset copy failed: {exc.__class__.__name__}")
            return {
                "script_src": None,
                "warnings": warnings,
                "asset_mode": "local",
                "source_asset_path": str(source),
                "local_asset_path": str(target),
                "local_asset_exists": target.exists(),
            }
        return {
            "script_src": self._relative_asset_src(target),
            "warnings": warnings,
            "asset_mode": "local",
            "source_asset_path": str(source),
            "local_asset_path": str(target),
            "local_asset_exists": target.exists(),
        }

    def _echarts_source_path(self) -> Path:
        configured = Path(str(self.settings.report_echarts_local_file or "echarts.min.js"))
        if configured.is_absolute():
            return configured
        return Path(__file__).resolve().parents[1] / "assets" / configured.name

    def _chart_asset_dir_path(self) -> Path:
        asset_dir = Path(str(self.settings.report_chart_asset_dir or "reports/assets"))
        if asset_dir.is_absolute():
            return asset_dir
        output_dir = Path(self.settings.report_output_dir)
        parts = asset_dir.parts
        if parts and parts[0] in {output_dir.name, "reports"}:
            suffix = Path(*parts[1:]) if len(parts) > 1 else Path()
            return output_dir / suffix
        return output_dir / asset_dir

    def _relative_asset_src(self, target: Path) -> str:
        output_dir = Path(self.settings.report_output_dir)
        try:
            return target.resolve().relative_to(output_dir.resolve()).as_posix()
        except ValueError:
            try:
                return Path(os.path.relpath(target, output_dir)).as_posix()
            except ValueError:
                return target.name

    def _chart_asset_head(self, chart_runtime: dict[str, Any]) -> str:
        if self._use_echarts(chart_runtime) and chart_runtime.get("script_src"):
            return f'<script src="{self._e(chart_runtime.get("script_src"))}"></script>'
        return ""

    def _chart_scripts(self, chart_runtime: dict[str, Any]) -> str:
        if not self._use_echarts(chart_runtime) or not chart_runtime.get("charts"):
            return ""
        chart_data = {"charts": chart_runtime.get("charts") or []}
        json_payload = json.dumps(chart_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return f"""
<script type="application/json" id="chart-data-report">{json_payload}</script>
<script type="application/json" id="chart-data">{json_payload}</script>
<script>
(function () {{
  const palette = ['#2563eb', '#059669', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2'];
  function readPayload() {{
    const node = document.getElementById('chart-data-report') || document.getElementById('chart-data');
    if (!node) return {{ charts: [], parseError: false }};
    try {{
      const parsed = JSON.parse(node.textContent || '{{"charts":[]}}');
      parsed.parseError = false;
      return parsed;
    }} catch (error) {{
      console.warn('Could not parse chart data', error);
      return {{ charts: [], parseError: true }};
    }}
  }}
  function compactNumber(value, unit) {{
    if (value === null || value === undefined || value === '') return 'Chưa xác minh';
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return String(value);
    const abs = Math.abs(numeric);
    let formatted;
    if (abs >= 1000000000) formatted = (numeric / 1000000000).toFixed(1).replace(/\\.0$/, '') + 'B';
    else if (abs >= 1000000) formatted = (numeric / 1000000).toFixed(1).replace(/\\.0$/, '') + 'M';
    else if (abs >= 1000) formatted = (numeric / 1000).toFixed(1).replace(/\\.0$/, '') + 'K';
    else formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2).replace(/\\.00$/, '').replace(/0$/, '');
    return unit ? formatted + ' ' + unit : formatted;
  }}
  function setEmpty(el, message) {{
    if (!el) return;
    el.textContent = '';
    const box = document.createElement('div');
    box.className = 'chart-empty';
    box.textContent = message;
    el.appendChild(box);
  }}
  function fallbackAll(message) {{
    document.querySelectorAll('[data-chart-id], [data-echart-id]').forEach(function (el) {{ setEmpty(el, message); }});
  }}
  function tooltipFormatter(params, chart) {{
    const rows = Array.isArray(params) ? params : [params];
    const title = rows[0] && rows[0].axisValueLabel ? rows[0].axisValueLabel : '';
    const body = rows.map(function (row) {{
      const unit = row.seriesName && chart.unitBySeries ? chart.unitBySeries[row.seriesName] : chart.unit;
      return row.marker + ' ' + row.seriesName + ': <b>' + compactNumber(row.value, unit || '') + '</b>';
    }}).join('<br>');
    return title ? '<b>' + title + '</b><br>' + body : body;
  }}
  function lineOption(chart) {{
    const series = (chart.series || []).map(function (item, index) {{
      return {{
        name: item.name,
        type: item.chartType || 'line',
        data: item.values || [],
        yAxisIndex: item.yAxisIndex || 0,
        smooth: item.chartType === 'bar' ? false : true,
        showSymbol: false,
        symbolSize: 5,
        lineStyle: {{ width: 3 }},
        itemStyle: {{ color: palette[index % palette.length] }},
        areaStyle: item.area ? {{ opacity: 0.08 }} : undefined,
        barMaxWidth: 24
      }};
    }});
    const hasSecondAxis = series.some(function (item) {{ return item.yAxisIndex === 1; }});
    return {{
      color: palette,
      tooltip: {{ trigger: 'axis', formatter: function (params) {{ return tooltipFormatter(params, chart); }} }},
      legend: {{ top: 4, type: 'scroll', textStyle: {{ color: '#475569' }} }},
      grid: {{ left: 48, right: hasSecondAxis ? 56 : 24, top: 52, bottom: 36, containLabel: true }},
      xAxis: {{ type: 'category', boundaryGap: false, data: chart.x || [], axisLabel: {{ color: '#64748b' }}, axisLine: {{ lineStyle: {{ color: '#d9dee7' }} }} }},
      yAxis: hasSecondAxis ? [
        {{ type: 'value', axisLabel: {{ color: '#64748b', formatter: function (v) {{ return compactNumber(v, chart.unit || ''); }} }}, splitLine: {{ lineStyle: {{ color: '#eef2f7' }} }} }},
        {{ type: 'value', axisLabel: {{ color: '#64748b', formatter: function (v) {{ return compactNumber(v, chart.secondaryUnit || ''); }} }}, splitLine: {{ show: false }} }}
      ] : {{ type: 'value', axisLabel: {{ color: '#64748b', formatter: function (v) {{ return compactNumber(v, chart.unit || ''); }} }}, splitLine: {{ lineStyle: {{ color: '#eef2f7' }} }} }},
      series: series
    }};
  }}
  function horizontalBarOption(chart) {{
    const categories = chart.x || [];
    const values = chart.series && chart.series[0] ? chart.series[0].values || [] : [];
    return {{
      color: palette,
      tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, valueFormatter: function (v) {{ return compactNumber(v, chart.unit || ''); }} }},
      grid: {{ left: 110, right: 24, top: 24, bottom: 24, containLabel: true }},
      xAxis: {{ type: 'value', min: 0, max: chart.max || null, axisLabel: {{ color: '#64748b' }}, splitLine: {{ lineStyle: {{ color: '#eef2f7' }} }} }},
      yAxis: {{ type: 'category', data: categories, axisLabel: {{ color: '#334155' }} }},
      series: [{{ name: chart.title, type: 'bar', data: values, barMaxWidth: 18, label: {{ show: true, position: 'right', formatter: function (p) {{ return compactNumber(p.value, chart.unit || ''); }} }} }}]
    }};
  }}
  function verticalBarOption(chart) {{
    const values = chart.series && chart.series[0] ? chart.series[0].values || [] : [];
    return {{
      color: palette,
      tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }}, valueFormatter: function (v) {{ return compactNumber(v, chart.unit || ''); }} }},
      grid: {{ left: 48, right: 24, top: 44, bottom: 36, containLabel: true }},
      xAxis: {{ type: 'category', data: chart.x || [], axisLabel: {{ color: '#334155' }}, axisLine: {{ lineStyle: {{ color: '#d9dee7' }} }} }},
      yAxis: {{ type: 'value', axisLabel: {{ color: '#64748b', formatter: function (v) {{ return compactNumber(v, chart.unit || ''); }} }}, splitLine: {{ lineStyle: {{ color: '#eef2f7' }} }} }},
      series: [{{ name: chart.title, type: 'bar', data: values, barMaxWidth: 32, itemStyle: {{ borderRadius: [6, 6, 0, 0] }}, label: {{ show: true, position: 'top', formatter: function (p) {{ return compactNumber(p.value, chart.unit || ''); }} }} }}]
    }};
  }}
  function optionFor(chart) {{
    if (chart.chartType === 'bar-horizontal') return horizontalBarOption(chart);
    if (chart.chartType === 'bar') return verticalBarOption(chart);
    return lineOption(chart);
  }}
  function initCharts() {{
    const chartData = readPayload();
    if (chartData.parseError) {{
      fallbackAll('Dữ liệu biểu đồ chưa sẵn sàng trong lần xuất báo cáo này.');
      return;
    }}
    const charts = Array.isArray(chartData.charts) ? chartData.charts : [];
    if (!charts.length) {{
      fallbackAll('Chưa đủ dữ liệu để dựng biểu đồ này.');
      return;
    }}
    if (!window.echarts) {{
      fallbackAll('Không tải được thư viện biểu đồ cục bộ. Báo cáo vẫn hiển thị bảng số liệu.');
      return;
    }}
    const instances = [];
    const renderedIds = {{}};
    charts.forEach(function (chart) {{
      if (!chart || !chart.id) return;
      const selector = '[data-chart-id="' + String(chart.id).replace(/"/g, '\\\\"') + '"], [data-echart-id="' + String(chart.id).replace(/"/g, '\\\\"') + '"]';
      const el = document.querySelector(selector) || document.getElementById('chart-' + chart.id);
      if (!el) return;
      try {{
        const instance = window.echarts.init(el, null, {{ renderer: 'canvas' }});
        instance.setOption(optionFor(chart));
        instances.push(instance);
        renderedIds[chart.id] = true;
      }} catch (error) {{
        console.warn('Chart init failed', chart.id, error);
        setEmpty(el, 'Không thể dựng biểu đồ này trong lần mở báo cáo.');
      }}
    }});
    document.querySelectorAll('[data-chart-id], [data-echart-id]').forEach(function (el) {{
      const id = el.getAttribute('data-chart-id') || el.getAttribute('data-echart-id');
      if (id && !renderedIds[id] && el.textContent.indexOf('Đang chuẩn bị biểu đồ') !== -1) {{
        setEmpty(el, 'Chưa đủ dữ liệu để dựng biểu đồ này.');
      }}
    }});
    const resizeAll = function () {{ instances.forEach(function (instance) {{ try {{ instance.resize(); }} catch (error) {{}} }}); }};
    window.addEventListener('resize', resizeAll);
    if (window.ResizeObserver) {{
      const observer = new ResizeObserver(resizeAll);
      document.querySelectorAll('.echart-box').forEach(function (el) {{ observer.observe(el); }});
    }}
  }}
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initCharts);
  }} else {{
    initCharts();
  }}
}})();
</script>
"""

    def _use_echarts(self, chart_runtime: dict[str, Any] | None) -> bool:
        return isinstance(chart_runtime, dict) and chart_runtime.get("engine") == "echarts"

    def _chart_engine(self, chart_runtime: dict[str, Any] | None) -> str:
        if isinstance(chart_runtime, dict):
            return self._chart_engine_name(chart_runtime.get("engine"))
        return self._chart_engine_name(self.settings.report_chart_engine)

    def _echart_card(self, chart_id: str, chart_runtime: dict[str, Any] | None) -> str:
        if not self._use_echarts(chart_runtime):
            return ""
        chart = self._dict(self._dict(chart_runtime).get("charts_by_id")).get(chart_id)
        if not chart:
            return ""
        box_class = "echart-box echart-box--compact" if chart.get("chartType") == "bar-horizontal" else "echart-box"
        return f"""
<div class="echart-card">
  <div class="chart-heading">
    <div>
      <h3>{self._e(self._text(chart.get("title"), "Biểu đồ"))}</h3>
      <p>{self._e(self._text(chart.get("subtitle"), "Dữ liệu xác thực hiện có"))}</p>
    </div>
    <span class="pill">{self._e(self._text(chart.get("badge"), "ECharts"))}</span>
  </div>
  <div id="chart-{self._e(chart_id)}" class="{box_class}" data-chart-id="{self._e(chart_id)}" data-echart-id="{self._e(chart_id)}">
    <div class="chart-empty">Đang chuẩn bị biểu đồ...</div>
  </div>
</div>
"""

    def _echart_grid(self, chart_ids: list[str], chart_runtime: dict[str, Any] | None) -> str:
        cards = [self._echart_card(chart_id, chart_runtime) for chart_id in chart_ids]
        cards = [card for card in cards if card]
        if not cards:
            return ""
        return '<div class="chart-grid chart-grid--two">' + "".join(cards) + "</div>"

    def _build_chart_data_payload(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        charts: list[dict[str, Any]] = []
        for chart in self.build_financial_chart_data(summary):
            charts.append(chart)
        score_chart = self.build_score_chart_data(summary)
        if score_chart:
            charts.append(score_chart)
        price_chart = self.build_price_chart_data(summary)
        if price_chart:
            charts.append(price_chart)
        for chart in self.build_peer_chart_data(summary):
            charts.append(chart)
        market_chart = self.build_market_chart_data(summary)
        if market_chart:
            charts.append(market_chart)
        return charts

    def build_financial_chart_data(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        bctc = self._dict(summary.get("bctc_3q"))
        periods = self._sort_periods_chronological(self._list_dicts(bctc.get("periods")))[:8]
        if len(periods) < 2:
            return []
        is_bank = self._has_bank_metrics(periods)
        if is_bank:
            definitions = [
                (
                    "financial-profit-trend",
                    "Xu hướng kết quả kinh doanh",
                    "Đơn vị: tỷ đồng, nếu nguồn dữ liệu cung cấp",
                    [
                        ("net_interest_income", "Thu nhập lãi thuần", "tỷ"),
                        ("profit_before_tax", "LNTT", "tỷ"),
                        ("profit_after_tax", "LNST", "tỷ"),
                        ("parent_profit", "LNST cổ đông mẹ", "tỷ"),
                    ],
                ),
                (
                    "financial-balance-scale",
                    "Quy mô bảng cân đối",
                    "Đơn vị: tỷ đồng, nếu nguồn dữ liệu cung cấp",
                    [
                        ("total_assets", "Tổng tài sản", "tỷ"),
                        ("customer_loans", "Cho vay KH", "tỷ"),
                        ("customer_deposits", "Tiền gửi KH", "tỷ"),
                        ("equity", "Vốn chủ sở hữu", "tỷ"),
                    ],
                ),
                (
                    "financial-ratio-trend",
                    "Xu hướng định giá và sinh lời",
                    "P/E, P/B và ROE theo kỳ có dữ liệu",
                    [("roe", "ROE", "%"), ("pe", "P/E", "x"), ("pb", "P/B", "x")],
                ),
            ]
        else:
            definitions = [
                (
                    "financial-profit-trend",
                    "Xu hướng kết quả kinh doanh",
                    "Đơn vị: tỷ đồng, nếu nguồn dữ liệu cung cấp",
                    [
                        ("revenue", "Doanh thu", "tỷ"),
                        ("gross_profit", "LN gộp", "tỷ"),
                        ("profit_before_tax", "LNTT", "tỷ"),
                        ("profit_after_tax", "LNST", "tỷ"),
                        ("parent_profit", "LNST cổ đông mẹ", "tỷ"),
                    ],
                ),
                (
                    "financial-balance-scale",
                    "Quy mô bảng cân đối",
                    "Đơn vị: tỷ đồng, nếu nguồn dữ liệu cung cấp",
                    [("total_assets", "Tổng tài sản", "tỷ"), ("equity", "Vốn chủ sở hữu", "tỷ"), ("total_liabilities", "Nợ phải trả", "tỷ")],
                ),
                (
                    "financial-ratio-trend",
                    "Xu hướng định giá và sinh lời",
                    "P/E, P/B, ROE và EPS theo kỳ có dữ liệu",
                    [("roe", "ROE", "%"), ("pe", "P/E", "x"), ("pb", "P/B", "x"), ("eps", "EPS", "VND")],
                ),
            ]
        charts = []
        for chart_id, title, subtitle, series_defs in definitions:
            chart = self._build_multi_series_chart(chart_id, title, subtitle, periods, series_defs)
            if chart:
                charts.append(chart)
        return charts

    def build_score_chart_data(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        scores = self._dict(summary.get("scores"))
        definitions = [
            ("valuation_score", "Định giá"),
            ("quality_score", "Chất lượng"),
            ("growth_score", "Tăng trưởng"),
            ("momentum_score", "Động lượng giá"),
            ("liquidity_score", "Thanh khoản"),
            ("size_score", "Quy mô"),
            ("risk_score", "Rủi ro"),
            ("score_confidence", "Tin cậy dữ liệu"),
        ]
        labels: list[str] = []
        values: list[float] = []
        for key, label in definitions:
            value = self._num(scores.get(key))
            if value is None:
                continue
            if key == "score_confidence" and 0 <= value <= 1:
                value *= 100
            labels.append(label)
            values.append(round(max(0, min(100, value)), 2))
        if not values:
            return None
        return {
            "id": "score-dashboard",
            "title": "Dashboard điểm định lượng",
            "subtitle": "Thang 0-100; riêng rủi ro càng cao càng cần thận trọng",
            "chartType": "bar-horizontal",
            "x": labels,
            "series": [{"name": "Điểm", "values": values}],
            "unit": "điểm",
            "max": 100,
            "badge": "Score",
        }

    def build_price_chart_data(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        history = self._list_dicts(summary.get("price_history"))
        labels: list[str] = []
        closes: list[float] = []
        volumes: list[float | None] = []
        for item in history:
            close_value = self._num(self._first_value(item, "close_price", "close", "last_price"))
            if close_value is None:
                continue
            labels.append(self._text(self._first_value(item, "time", "date", "trading_date", "time_id"), ""))
            closes.append(close_value)
            volumes.append(self._num(self._first_value(item, "volume", "total_volume", "trading_volume")))
        if len(closes) < 2:
            return None
        series = [{"name": "Giá đóng cửa", "values": closes, "unit": "VND", "area": True}]
        valid_volumes = [value for value in volumes if value is not None]
        unit_by_series = {"Giá đóng cửa": "VND"}
        if len(valid_volumes) >= 2:
            series.append({"name": "Khối lượng", "values": volumes, "unit": "cp", "chartType": "bar", "yAxisIndex": 1})
            unit_by_series["Khối lượng"] = "cp"
        return {
            "id": "price-close-trend",
            "title": "Diễn biến giá và thanh khoản",
            "subtitle": "Giá đóng cửa và khối lượng trong chuỗi dữ liệu hiện có",
            "chartType": "line",
            "x": labels,
            "series": series,
            "unit": "VND",
            "secondaryUnit": "cp",
            "unitBySeries": unit_by_series,
            "badge": "Giá",
        }

    def build_peer_chart_data(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        peer = self._dict(summary.get("industry_peer_context"))
        peers = self._list_dicts(peer.get("peers"))
        charts: list[dict[str, Any]] = []
        for chart_id, title, value_key, fallback_key, unit in [
            ("peer-market-cap", "So sánh vốn hóa peer", "market_cap_billion", "market_cap", "tỷ"),
            ("peer-pe-comparison", "So sánh P/E peer", "pe_basic", "pe", "x"),
            ("peer-roe-comparison", "So sánh ROE peer", "roe", None, "%"),
        ]:
            labels: list[str] = []
            values: list[float] = []
            for item in peers[:8]:
                value = self._num(item.get(value_key))
                if value is None and fallback_key:
                    value = self._num(item.get(fallback_key))
                if value is None:
                    continue
                labels.append(self._text(item.get("symbol"), "Peer"))
                values.append(value)
            if len(values) >= 2:
                charts.append(
                    {
                        "id": chart_id,
                        "title": title,
                        "subtitle": "Chỉ dùng peer có số liệu định lượng xác thực",
                        "chartType": "bar",
                        "x": labels,
                        "series": [{"name": title, "values": values}],
                        "unit": unit,
                        "badge": "Peer",
                    }
                )
        return charts

    def build_market_chart_data(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        if self._market_chart_type() != "echarts_bar":
            return None
        presentation = self._presentation(summary)
        view = self._dict(presentation.get("market_context_view"))
        value = self._market_health_score(summary, view)
        if value is None:
            return None
        label, _ = self._market_health_status(value)
        return {
            "id": "market-health-score",
            "title": "Thước đo sức khỏe thị trường",
            "subtitle": "0 là thận trọng hơn, 100 là tích cực hơn",
            "chartType": "bar-horizontal",
            "x": ["Sức khỏe thị trường"],
            "series": [{"name": "Điểm", "values": [value]}],
            "unit": "điểm",
            "max": 100,
            "label": label,
            "badge": "Market",
        }

    def _build_multi_series_chart(
        self,
        chart_id: str,
        title: str,
        subtitle: str,
        periods: list[dict[str, Any]],
        definitions: list[tuple[str, str, str]],
    ) -> dict[str, Any] | None:
        labels = [self._text(period.get("period"), "Kỳ") for period in periods]
        series = []
        unit_by_series: dict[str, str] = {}
        for key, label, unit in definitions:
            values: list[float | None] = []
            valid_count = 0
            for period in periods:
                value = self._num(self._financial_value(period, key))
                values.append(value)
                if value is not None:
                    valid_count += 1
            if valid_count >= 2:
                series.append({"name": label, "values": values, "unit": unit})
                unit_by_series[label] = unit
        if not series:
            return None
        return {
            "id": chart_id,
            "title": title,
            "subtitle": subtitle,
            "chartType": "line",
            "x": labels,
            "series": series,
            "unit": series[0].get("unit") if series else "",
            "unitBySeries": unit_by_series,
            "badge": "BCTC",
        }

    def _sort_periods_chronological(self, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        indexed = list(enumerate(periods))
        return [period for _, period in sorted(indexed, key=lambda item: self._period_sort_key(item[1], item[0]))]

    def _period_sort_key(self, period: dict[str, Any], index: int) -> tuple[int, int, int]:
        label = str(period.get("period") or "").strip().upper()
        match = re.search(r"Q([1-4])\s*/\s*(20\d{2}|19\d{2})", label)
        if match:
            return (int(match.group(2)), int(match.group(1)), index)
        year = period.get("year")
        quarter = period.get("quarter")
        if isinstance(year, int):
            return (year, int(quarter) if isinstance(quarter, int) else 4, index)
        match_year = re.search(r"(20\d{2}|19\d{2})", label)
        if match_year:
            return (int(match_year.group(1)), 4, index)
        return (0, 0, index)

    def _score_bar_chart(self, score_cards: list[Any]) -> str:
        rows = []
        for card in score_cards:
            if not isinstance(card, dict) or card.get("key") == "data_confidence":
                continue
            score = card.get("score")
            if not isinstance(score, (int, float)):
                continue
            pct = self._score_pct(score)
            rows.append(
                f"""
<div class="bar-row">
  <span>{self._e(self._text(card.get("label"), "Điểm"))}</span>
  <div class="bar-track"><span class="bar-fill" style="width:{pct}%"></span></div>
  <strong class="right">{self._e(self._value(score))}</strong>
</div>
"""
            )
        body = "".join(rows) if rows else "<p>Chưa đủ dữ liệu điểm số để dựng biểu đồ.</p>"
        return f'<div class="chart-panel"><h3>Biểu đồ điểm định lượng</h3>{body}</div>'

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
                    "meter_percent": self._score_pct(score) if score is not None else None,
                    "display_value": str(score) if score is not None else None,
                    "scale": "0-100",
                    "score_label": self._score_label(score, inverse=(key == "risk_score")),
                    "reason": "Điểm được tính từ các dữ liệu định lượng hiện có.",
                    "data_used": data_used,
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

    def _price_momentum_chart(self, summary: dict[str, Any]) -> str:
        history = self._list_dicts(summary.get("price_history"))
        closes = [self._first_value(item, "close_price", "close") for item in history]
        values = [float(value) for value in closes if isinstance(value, (int, float))]
        if len(values) < 2:
            return '<div class="chart-panel"><h3>Đường giá tham khảo</h3><p>Chuỗi giá chưa đủ dài để dựng biểu đồ.</p></div>'
        points = self._polyline_points(values, width=320, height=120, padding=12)
        area = f"M12,132 L{points} L308,132 Z" if points else ""
        return f"""
<div class="chart-panel">
  <h3>Đường giá tham khảo</h3>
  <svg viewBox="0 0 320 150" role="img" aria-label="Biểu đồ giá">
    <line class="chart-axis" x1="12" y1="132" x2="308" y2="132"></line>
    <path class="chart-area" d="{self._e(area)}"></path>
    <polyline class="chart-line" points="{self._e(points)}"></polyline>
  </svg>
  <p class="muted">Từ {self._e(self._value(values[0]))} đến {self._e(self._value(values[-1]))}; chỉ phản ánh chuỗi dữ liệu hiện có.</p>
</div>
"""

    def _financial_trend_table(self, periods: list[Any]) -> str:
        if self._has_bank_metrics(periods):
            return self._bank_financial_table(periods)
        rows = []
        for period in periods[:6]:
            if not isinstance(period, dict):
                continue
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
        return self._table(
            ["Kỳ", "Doanh thu", "LN gộp", "LNTT", "LNST", "EPS", "Tổng tài sản", "Nợ phải trả", "Vốn chủ", "P/E", "P/B", "ROE", "ROA"],
            rows,
        )

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

    def _financial_value(self, period: dict[str, Any], key: str) -> Any:
        if not isinstance(period, dict):
            return None
        if key in {"total_assets", "equity", "customer_loans", "customer_deposits", "roa", "roe"}:
            return StockDataService.sanitize_financial_period(period).get(key)
        return period.get(key)

    def _bank_financial_table(self, periods: list[Any]) -> str:
        rows = []
        for period in periods[:6]:
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
        return self._table(
            ["Kỳ", "Thu nhập lãi thuần", "Thu nhập dịch vụ thuần", "LN trước dự phòng", "Dự phòng", "LNTT", "LNST", "EPS", "Tổng tài sản", "Cho vay KH", "Tiền gửi KH", "Vốn chủ", "P/E", "P/B", "NIM", "Nợ xấu", "ROE", "ROA"],
            rows,
        )

    def _financial_balance_table(self, financial: dict[str, Any], *, is_bank: bool = False) -> str:
        if is_bank:
            rows = [
                ("Tổng tài sản", self._financial_value(financial, "total_assets")),
                ("Cho vay khách hàng", self._financial_value(financial, "customer_loans")),
                ("Tiền gửi khách hàng", self._financial_value(financial, "customer_deposits")),
                ("Tiền gửi tại NHNN", financial.get("deposit_at_state_bank")),
                ("Chứng khoán đầu tư", financial.get("investment_securities")),
                ("Phát hành giấy tờ có giá", financial.get("valuable_papers_issued")),
                ("Vốn chủ sở hữu", self._financial_value(financial, "equity")),
                ("P/E", financial.get("pe")),
                ("P/B", financial.get("pb")),
                ("ROE", self._financial_value(financial, "roe")),
                ("ROA", self._financial_value(financial, "roa")),
            ]
        else:
            rows = [
                ("Tổng tài sản", self._financial_value(financial, "total_assets")),
                ("Nợ phải trả", financial.get("total_liabilities")),
                ("Vốn chủ sở hữu", self._financial_value(financial, "equity")),
                ("Tài sản ngắn hạn", financial.get("current_assets")),
                ("Nợ ngắn hạn", financial.get("current_liabilities")),
                ("Tiền và tương đương tiền", financial.get("cash")),
                ("Hàng tồn kho", financial.get("inventory")),
                ("P/E", financial.get("pe")),
                ("P/B", financial.get("pb")),
                ("ROE", self._financial_value(financial, "roe")),
            ]
        return self._table(["Chỉ tiêu", "Giá trị"], rows)

    def _financial_trend_chart(self, periods: list[Any]) -> str:
        series = self.build_financial_chart_series(periods)
        if not series:
            return f'<div class="financial-charts-grid">{self._financial_metric_cards(periods)}</div>'
        charts = []
        for key, payload in list(series.items())[:4]:
            points_payload = payload.get("points") if isinstance(payload, dict) else []
            values = [float(point["value"]) for point in points_payload if isinstance(point, dict)]
            labels = [self._text(point.get("period"), "") for point in points_payload if isinstance(point, dict)]
            if len(values) < 2:
                continue
            points = self._polyline_points(values, width=320, height=120, padding=12)
            charts.append(
                f"""
<div class="chart-panel">
  <h3>{self._e(self._text(payload.get("label"), key))}</h3>
  <svg viewBox="0 0 320 150" role="img" aria-label="{self._e(self._text(payload.get("label"), key))}">
    <line class="chart-axis" x1="12" y1="132" x2="308" y2="132"></line>
    <polyline class="chart-line" points="{self._e(points)}"></polyline>
  </svg>
  <p class="muted">{self._e(labels[0] if labels else 'Kỳ đầu')} → {self._e(labels[-1] if labels else 'kỳ cuối')}; chỉ dùng các điểm có số liệu xác thực.</p>
</div>
"""
            )
        if not charts:
            return f'<div class="financial-charts-grid">{self._financial_metric_cards(periods)}</div>'
        return '<div class="financial-charts-grid">' + "".join(charts) + "</div>"

    def build_financial_chart_series(self, periods: list[Any]) -> dict[str, dict[str, Any]]:
        valid_periods = [period for period in periods if isinstance(period, dict)]
        chronological = list(reversed(valid_periods[:8]))
        if self._has_bank_metrics(valid_periods):
            definitions = [
                ("profit_after_tax", "Xu hướng lợi nhuận sau thuế"),
                ("parent_profit", "Xu hướng lợi nhuận cổ đông mẹ"),
                ("profit_before_tax", "Xu hướng lợi nhuận trước thuế"),
                ("net_interest_income", "Xu hướng thu nhập lãi thuần"),
                ("customer_loans", "Xu hướng cho vay khách hàng"),
                ("customer_deposits", "Xu hướng tiền gửi khách hàng"),
                ("total_assets", "Xu hướng tổng tài sản"),
                ("roe", "Xu hướng ROE"),
                ("roa", "Xu hướng ROA"),
                ("pb", "Xu hướng P/B"),
                ("pe", "Xu hướng P/E"),
            ]
        else:
            definitions = [
                ("revenue", "Xu hướng doanh thu"),
                ("gross_profit", "Xu hướng lợi nhuận gộp"),
                ("profit_after_tax", "Xu hướng lợi nhuận sau thuế"),
                ("parent_profit", "Xu hướng lợi nhuận cổ đông mẹ"),
                ("total_assets", "Xu hướng tổng tài sản"),
                ("equity", "Xu hướng vốn chủ sở hữu"),
                ("roe", "Xu hướng ROE"),
                ("pe", "Xu hướng P/E"),
                ("pb", "Xu hướng P/B"),
                ("eps", "Xu hướng EPS"),
                ("eps_ttm", "Xu hướng EPS TTM"),
                ("bvps", "Xu hướng BVPS"),
            ]
        result: dict[str, dict[str, Any]] = {}
        for key, label in definitions:
            points = []
            for period in chronological:
                value = self._num(self._financial_value(period, key))
                if value is None:
                    continue
                points.append({"period": self._text(period.get("period"), "Chưa xác minh"), "value": value})
            if len(points) >= 2:
                result[key] = {"label": label, "points": points}
        return result

    def _financial_metric_cards(self, periods: list[Any]) -> str:
        valid_periods = [period for period in periods if isinstance(period, dict)]
        latest = valid_periods[0] if valid_periods else {}
        labels = {
            "revenue": "Doanh thu",
            "profit_after_tax": "LNST",
            "parent_profit": "LN cổ đông mẹ",
            "total_assets": "Tổng tài sản",
            "equity": "Vốn chủ",
            "eps": "EPS",
            "eps_ttm": "EPS TTM",
            "bvps": "BVPS",
            "pe": "P/E",
            "pb": "P/B",
            "roe": "ROE",
            "roa": "ROA",
            "net_interest_income": "Thu nhập lãi thuần",
            "customer_loans": "Cho vay KH",
            "customer_deposits": "Tiền gửi KH",
        }
        rows = [
            (label, self._financial_value(latest, key))
            for key, label in labels.items()
            if isinstance(latest, dict) and self._num(self._financial_value(latest, key)) is not None
        ]
        if rows:
            return f'<div class="chart-panel"><h3>Chỉ tiêu tài chính kỳ gần nhất</h3>{self._table(["Chỉ tiêu", "Giá trị"], rows)}<p class="muted">Hiện chỉ có một kỳ hoặc chưa đủ chuỗi để dựng biểu đồ xu hướng.</p></div>'
        return '<div class="chart-panel"><h3>Xu hướng tài chính</h3><p>Chưa có đủ chỉ tiêu tài chính xác thực để dựng biểu đồ.</p></div>'

    def _industry_table(self, industry: dict[str, Any]) -> str:
        rows = [
            ("Ngành cấp cao", industry.get("industry_level_1") or industry.get("sector") or industry.get("sector_name")),
            ("Nhóm ngành", industry.get("industry_level_2") or industry.get("industry_group") or industry.get("group")),
            ("Ngành chi tiết", industry.get("industry_level_3") or industry.get("industry") or industry.get("industry_name")),
            ("Nguồn", self._source_display(industry.get("source")) if industry.get("source") else None),
        ]
        return self._table(["Nội dung", "Giá trị"], rows)

    def _industry_reference_table(self, group: Any, detail: Any, source: Any) -> str:
        rows = [
            ("Nhóm ngành", group),
            ("Ngành chi tiết", detail),
            ("Nguồn", source),
        ]
        return self._table(["Nội dung", "Giá trị"], rows)

    def _leadership_table(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<p>Chưa trích xuất được danh sách ban lãnh đạo từ nguồn công khai trong lần chạy này.</p>"
        table_rows = []
        for item in rows[:8]:
            table_rows.append(
                (
                    item.get("name"),
                    item.get("position") or item.get("title"),
                    item.get("shares"),
                    item.get("ownership_percent") if item.get("ownership_percent") is not None else item.get("ratio"),
                    item.get("ownership_note") or item.get("ownership_source") or self._source_display(item.get("source")),
                )
            )
        return self._table(["Họ tên", "Chức vụ", "Số cổ phiếu", "Tỷ lệ sở hữu", "Ghi chú"], table_rows)

    def _ownership_table(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<p>Chưa trích xuất được dữ liệu sở hữu đáng tin cậy từ nguồn công khai trong lần chạy này.</p>"
        table_rows = []
        for item in rows[:8]:
            table_rows.append(
                (
                    item.get("holder") or item.get("name"),
                    item.get("shares"),
                    item.get("ownership_percent") or item.get("ratio"),
                    self._source_display(item.get("source")),
                )
            )
        return self._table(["Cổ đông / Tổ chức / Cá nhân", "Số cổ phiếu", "Tỷ lệ sở hữu", "Ghi chú"], table_rows)

    def _has_peer_metrics(self, peer: dict[str, Any]) -> bool:
        metric_keys = (
            "close_price",
            "price",
            "change_1d_percent",
            "matched_volume",
            "matched_value_billion",
            "market_cap_billion",
            "market_cap",
            "eps_4q",
            "pe_basic",
            "pe",
            "pb",
            "roe",
            "rsi_14",
            "basic_score",
        )
        return sum(1 for key in metric_keys if self._num(peer.get(key)) is not None) >= 2

    def _qualitative_peer_cards(self, peers: list[dict[str, Any]]) -> str:
        if not peers:
            return "<p>Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận.</p>"
        cards = []
        for peer in peers[:8]:
            missing = self._text(peer.get("missing_data") or ", ".join(peer.get("missing_metrics") or []), "các chỉ tiêu định lượng chính")
            cards.append(
                f"""
<article class="peer-card">
  <h3>{self._e(self._text(peer.get("symbol"), "Mã"))}</h3>
  <p>{self._e(self._text(peer.get("company") or peer.get("company_name"), "Chưa xác minh tên doanh nghiệp"))}</p>
  <p class="muted">Được ghi nhận trong nguồn so sánh cùng ngành. Cần bổ sung: {self._e(missing)}.</p>
  <p><span class="pill">Cần chờ xác nhận</span></p>
</article>
"""
            )
        return '<div class="peer-card-grid">' + "".join(cards) + "</div>"

    def _peer_table(self, peers: list[Any]) -> str:
        rows = []
        for peer in peers[:8]:
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
        return self._table(["Mã", "Doanh nghiệp", "Giá", "% 1D", "GT giao dịch", "Vốn hóa", "EPS 4Q", "P/E", "P/B", "ROE", "Tín hiệu", "Nhận xét"], rows)

    def _peer_charts(self, peers: list[Any]) -> str:
        market_cap = self._peer_bar_chart(peers, value_key="market_cap_billion", fallback_key="market_cap", title="Vốn hóa peer", suffix=" tỷ")
        pe_chart = self._peer_bar_chart(peers, value_key="pe_basic", fallback_key="pe", title="P/E peer", suffix="x")
        rsi_chart = self._peer_bar_chart(peers, value_key="rsi_14", fallback_key=None, title="RSI peer", suffix="")
        charts = "".join(chart for chart in (market_cap, pe_chart, rsi_chart) if chart)
        if not charts:
            return ""
        return f'<div class="grid-2" style="margin-top:16px">{charts}</div>'

    def _peer_bar_chart(
        self,
        peers: list[Any],
        *,
        value_key: str,
        fallback_key: str | None,
        title: str,
        suffix: str,
    ) -> str:
        rows: list[tuple[str, float]] = []
        for peer in peers[:8]:
            if not isinstance(peer, dict):
                continue
            value = peer.get(value_key)
            if value is None and fallback_key:
                value = peer.get(fallback_key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                rows.append((self._text(peer.get("symbol"), ""), float(value)))
        if not rows:
            return ""
        max_value = max(abs(value) for _, value in rows) or 1
        body = []
        for symbol, value in rows:
            width = max(4, min(100, int(abs(value) / max_value * 100)))
            body.append(
                f"""
<div class="bar-row">
  <span>{self._e(symbol)}</span>
  <div class="bar-track"><span class="bar-fill" style="width:{width}%"></span></div>
  <strong class="right">{self._e(self._value(value))}{self._e(suffix)}</strong>
</div>
"""
            )
        return f'<div class="chart-panel"><h3>{self._e(title)}</h3>{"".join(body)}</div>'

    def _reference_candidate_table(self, candidates: Any) -> str:
        if not isinstance(candidates, list) or not candidates:
            return "<p>Chưa đủ dữ liệu xác thực để lập danh sách mã cùng ngành có thể so sánh định lượng.</p>"
        cards = []
        for item in candidates[:6]:
            if not isinstance(item, dict):
                continue
            supporting_data = self._supporting_data_text(self._dict(item.get("supporting_data")))
            available_data = item.get("available_data") or supporting_data
            missing_data = item.get("missing_data") or "Không ghi nhận khoảng trống chính"
            cards.append(
                f"""
<article class="peer-card">
  <h3>{self._e(self._text(item.get("ticker") or item.get("symbol"), "Mã"))} — {self._e(self._text(item.get("label"), "Đáng theo dõi"))}</h3>
  <p><strong>{self._e(self._text(item.get("company") or item.get("company_name"), "Chưa xác minh doanh nghiệp"))}</strong></p>
  <p><strong>Vì sao:</strong> {self._e(self._text(item.get("reason_to_watch"), "Cùng nhóm ngành và có dữ liệu để đối chiếu sơ bộ."))}</p>
  <p><strong>Điểm mạnh:</strong> {self._e(self._text(item.get("strengths") or supporting_data, "Cần bổ sung dữ liệu trước khi so sánh sâu."))}</p>
  <p><strong>Cần kiểm tra:</strong> {self._e(self._text(item.get("key_risk"), "Cần đối chiếu quy mô, chất lượng tài sản và kết quả kinh doanh gần nhất."))}</p>
  <p><strong>Dữ liệu đã có:</strong> {self._e(self._text(available_data, "Chưa xác minh"))}</p>
  <p><strong>Dữ liệu còn thiếu:</strong> {self._e(self._text(missing_data, "Không ghi nhận khoảng trống chính"))}</p>
  <p class="muted">Tỷ lệ tin cậy: {self._e(self._format_confidence(item.get("confidence")))} · Nguồn: {self._e(self._source_display(item.get("source")))}</p>
</article>
"""
            )
        return '<div class="peer-card-grid">' + "".join(cards) + "</div>" if cards else "<p>Chưa đủ dữ liệu xác thực để lập danh sách mã cùng ngành có thể so sánh định lượng.</p>"

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

    def _peer_metric_explain(self) -> str:
        return """
<details class="metric-explain">
  <summary>Cách đọc bảng peer</summary>
  <p>P/E: mức giá thị trường đang trả cho mỗi đồng lợi nhuận. P/B: mức giá thị trường so với giá trị sổ sách. ROE: hiệu quả tạo lợi nhuận trên vốn chủ sở hữu. Vốn hóa: quy mô thị trường của doanh nghiệp. Thanh khoản: mức độ dễ mua/bán dựa trên khối lượng hoặc giá trị giao dịch.</p>
</details>
"""

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

    def _position_sizing_table(self, position: dict[str, Any]) -> str:
        if not position:
            return "<p>Chưa có thông số vốn/tỷ trọng được xác thực trong request.</p>"
        rows = [
            ("Vốn tham chiếu", position.get("capital_vnd")),
            ("Rủi ro mỗi giao dịch", position.get("risk_per_trade_pct")),
            ("Tỷ trọng tối đa", position.get("max_position_pct")),
        ]
        return self._table(["Thông số", "Giá trị"], rows)

    def _research_group(self, label: str, items: Any) -> str:
        if not isinstance(items, list) or not items:
            return ""
        cards = "".join(self._research_card(item) for item in items if isinstance(item, dict))
        return f'<div class="research-group"><h3>{self._e(label)}</h3><div class="news-grid">{cards}</div></div>'

    def _research_card(self, item: dict[str, Any]) -> str:
        title = self._text(item.get("title"), "Nguồn chưa có tiêu đề")
        url = self._safe_url(item.get("url"))
        confidence_badge = self._format_confidence(item.get("confidence")) if item.get("confidence") is not None else item.get("confidence_label")
        badges = [item.get("tone"), item.get("impact_horizon"), confidence_badge]
        badges_html = "".join(f'<span class="badge">{self._e(self._text(badge, ""))}</span>' for badge in badges if badge)
        factors = item.get("affected_factors") if isinstance(item.get("affected_factors"), list) else []
        factor_html = "".join(f'<span class="badge">{self._e(self._text(factor, ""))}</span>' for factor in factors[:4])
        return f"""
<article class="news-card">
  <div>
    <h3 class="news-card__title"><a href="{self._e(url)}" target="_blank" rel="noopener noreferrer">{self._e(title)}</a></h3>
    <p class="muted">{self._e(self._text(item.get("source"), "Chưa rõ nguồn"))} · {self._e(self._text(item.get("display_date"), "Chưa xác minh"))}</p>
    <div class="news-badges">{badges_html}{factor_html}</div>
    <p class="news-card__snippet">{self._e(self._text(item.get("detailed_summary"), "Cần mở nguồn gốc để kiểm chứng nội dung."))}</p>
    <p><strong>Tác động có thể có:</strong> {self._e(self._text(item.get("possible_impact"), "Chưa xác minh"))}</p>
  </div>
  <div class="news-card__footer">
    <p class="muted">Cần kiểm tra: {self._e(self._text(item.get("what_to_verify"), "Mở URL nguồn để xác minh."))}</p>
  </div>
</article>
"""

    def _coverage_cards(self, rows: Any) -> str:
        if not isinstance(rows, list) or not rows:
            return "<p>Chưa có dữ liệu độ phủ.</p>"
        cards = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cards.append(
                f"""
<div class="coverage-card">
  <span class="pill">{self._e(self._text(row.get("status_label") or row.get("status"), "Cần kiểm tra"))}</span>
  <h3>{self._e(self._text(row.get("label") or row.get("group"), "Nhóm dữ liệu"))}</h3>
  <p>{self._e(self._text(row.get("description") or row.get("note"), "Chưa xác minh"))}</p>
</div>
"""
            )
        return '<div class="coverage-grid">' + "".join(cards) + "</div>" if cards else "<p>Chưa có dữ liệu độ phủ.</p>"

    def _friendly_source_list(self, data_sources: list[dict[str, Any]] | None) -> str:
        clean_sources = sanitize_data_source_statuses(data_sources or [])
        if not clean_sources:
            return "<p>Chưa có nguồn dữ liệu được ghi nhận.</p>"
        rows = []
        for source in clean_sources:
            if not isinstance(source, dict):
                continue
            rows.append(
                f"""
<div class="source-row">
  <span>{self._e(self._text(source.get("name"), "Nguồn dữ liệu"))}</span>
  <strong>{self._e(self._text(source.get("status_label"), source_status_label(source.get("status"))))}</strong>
  <small>{self._e(self._text(source.get("detail") or source.get("summary"), "Nguồn đã được đối chiếu."))}</small>
</div>
"""
            )
        return '<div class="source-list">' + "".join(rows) + "</div>" if rows else "<p>Chưa có nguồn dữ liệu được ghi nhận.</p>"

    def _friendly_source_name(self, value: Any) -> str:
        text = str(value or "").strip()
        mapping = {
            "Backend /api/stocks/:symbol/analysis-data": "Dữ liệu giá và thanh khoản",
            "Backend /api/stocks/:symbol": "Hồ sơ cổ phiếu",
            "Backend /api/stocks/:symbol/chart": "Chuỗi giá",
            "Backend /api/watchlists": "Danh sách theo dõi cá nhân",
            "External Research": "Tin tức/nghiên cứu bên ngoài",
            "CafeF company overview": "CafeF thông tin doanh nghiệp",
            "CafeF thông tin doanh nghiệp": "CafeF thông tin doanh nghiệp",
            "CafeF BCTC": "CafeF tài chính",
            "Vietstock Finance BCTT": "Vietstock Finance BCTC",
            "Vietstock Finance BCTC": "Vietstock Finance BCTC",
            "Vietstock peer cùng ngành": "Vietstock peer cùng ngành",
        }
        return mapping.get(text, to_user_facing_source_name(text))

    def _source_status_label(self, value: Any, *, name: Any = None, detail: Any = None) -> str:
        text = str(value or "").lower()
        if text == "success":
            return "Đã ghi nhận"
        if text == "partial":
            source_name = self._friendly_source_name(name)
            detail_text = str(detail or "").lower()
            if source_name == "CafeF thông tin doanh nghiệp" and "fields=0" in detail_text:
                return "Chưa trích xuất đủ"
            if ("peer" in source_name.lower() or "cùng ngành" in source_name.lower()) and "peers=0" in detail_text:
                return "Chưa trích xuất đủ"
            return "Ghi nhận một phần"
        if text == "insufficient":
            return "Chưa trích xuất đủ"
        if text == "failed":
            return "Chưa lấy được"
        if text == "disabled":
            return "Chưa cấu hình"
        return "Cần kiểm tra"

    def _friendly_source_note(self, name: Any, status: Any, detail: Any = None) -> str:
        source_name = self._friendly_source_name(name)
        status_text = str(status or "").lower()
        detail_text = str(detail or "").lower()
        if status_text == "failed":
            if source_name in {"Dữ liệu phân tích cổ phiếu", "Hồ sơ cổ phiếu", "Chuỗi giá"}:
                return "Nguồn dữ liệu nội bộ chưa phản hồi trong lần chạy này"
            return "Nguồn này chưa sẵn sàng trong lần chạy này"
        if status_text == "disabled":
            return "Nguồn này chưa được bật trong cấu hình"
        if status_text == "partial":
            if source_name == "CafeF thông tin doanh nghiệp":
                if "fields=0" in detail_text:
                    return "Trang đã được kiểm tra nhưng chưa có trường doanh nghiệp/ngành đủ sạch"
                return "Mới ghi nhận được một phần thông tin doanh nghiệp"
            if "BCTC" in source_name:
                return "Chỉ ghi nhận được một phần chỉ tiêu tài chính"
            if "peer" in source_name.lower() or "cùng ngành" in source_name.lower():
                if "peers=0" in detail_text:
                    return "Nguồn đã được kiểm tra nhưng chưa đủ dòng peer dùng được"
                return "Chưa đủ peer định lượng để so sánh"
            return "Dữ liệu mới được ghi nhận một phần"
        if status_text == "insufficient":
            if source_name == "CafeF thông tin doanh nghiệp":
                return "Trang đã được kiểm tra nhưng chưa đủ ban lãnh đạo/sở hữu hoặc hồ sơ sạch"
            if "peer" in source_name.lower() or "cùng ngành" in source_name.lower():
                return "Nguồn đã được kiểm tra nhưng chưa đủ dòng peer dùng được"
            return "Nguồn đã được kiểm tra nhưng chưa đủ dữ liệu dùng được"
        if "BCTC" in source_name:
            return "Dữ liệu báo cáo tài chính" if status_text == "success" else "Dữ liệu BCTC chưa đủ để dùng định lượng"
        if "peer" in source_name.lower() or "cùng ngành" in source_name.lower():
            return "Dữ liệu so sánh cùng ngành" if status_text == "success" else "Dữ liệu peer chưa đủ để so sánh định lượng"
        if source_name in {"Dữ liệu phân tích cổ phiếu", "Hồ sơ cổ phiếu"}:
            return "Giá, định giá và thanh khoản"
        if source_name == "Chuỗi giá":
            return "Dữ liệu diễn biến giá"
        if source_name == "Tin tức/nghiên cứu bên ngoài":
            return "Nguồn tin phù hợp"
        if source_name == "CafeF thông tin doanh nghiệp":
            return "Nguồn thông tin doanh nghiệp"
        if source_name in {"File Markdown", "File HTML"}:
            return "File báo cáo đã tạo"
        return "Nguồn dữ liệu tham khảo"

    def _score_card(self, card: dict[str, Any]) -> str:
        raw_score = card.get("score")
        raw_meter = card.get("meter_percent")
        display_value = card.get("display_value")
        is_confidence = "tin cậy" in self._text(card.get("label"), "").lower()
        if raw_meter is not None:
            meter = normalize_percent_score(raw_meter)
            score_pct = meter if meter is not None else 0
        elif isinstance(raw_score, float) and 0 <= raw_score <= 1 and is_confidence:
            score_pct = normalize_percent_score(raw_score) or 0
        elif isinstance(raw_score, (int, float)):
            score_pct = max(0, min(100, int(round(raw_score))))
        else:
            score_pct = 0
        if display_value not in (None, ""):
            score_text = str(display_value)
        elif isinstance(raw_score, (int, float)):
            score_text = self._format_confidence(raw_score) if is_confidence else (str(int(raw_score)) if float(raw_score).is_integer() else f"{raw_score:.2f}")
        else:
            score_text = "N/A"
        tag = card.get("tag") or card.get("score_label")
        description = card.get("description") or card.get("reason")
        return f"""
<article class="score-card">
  <header><strong>{self._e(self._text(card.get("label"), "Điểm"))}</strong><span class="score-number">{self._e(score_text)}</span></header>
  <div class="score-meter"><span style="width:{score_pct}%"></span></div>
  <p><span class="pill">{self._e(self._text(tag, "Chưa xác minh"))}</span></p>
  <p>{self._e(self._text(description, "Cần kiểm tra thêm dữ liệu."))}</p>
  <p class="muted">Dữ liệu dùng: {self._e(self._text(card.get("data_used"), "Chưa xác minh"))}</p>
</article>
"""

    def _roadmap_html(self, roadmap: Any) -> str:
        if not isinstance(roadmap, list) or not roadmap:
            return "<p>Chưa có lộ trình theo dõi được xác thực.</p>"
        steps = []
        for item in roadmap:
            if not isinstance(item, dict):
                continue
            steps.append(
                f"""
<div class="timeline-card">
  <strong>{self._e(self._text(item.get("phase"), "Giai đoạn"))}</strong>
  <p class="muted">{self._e(self._text(item.get("horizon"), "Chưa xác minh"))}</p>
  <p>{self._e(self._text(item.get("focus"), "Cần kiểm tra thêm dữ liệu."))}</p>
</div>
"""
            )
        return '<div class="timeline">' + ''.join(steps) + '</div>' if steps else "<p>Chưa có lộ trình theo dõi được xác thực.</p>"

    def _research_insight_lists(self, insights: dict[str, Any]) -> str:
        labels = [
            ("positive_catalysts", "Catalyst tích cực"),
            ("risks", "Rủi ro/tín hiệu tiêu cực"),
            ("background", "Bối cảnh trung tính"),
            ("needs_verification", "Cần kiểm chứng"),
        ]
        blocks = []
        for key, label in labels:
            items = insights.get(key)
            if not isinstance(items, list) or not items:
                continue
            short_items = []
            for item in items[:4]:
                if isinstance(item, dict):
                    title = self._text(item.get("title"), "Nguồn chưa có tiêu đề")
                    why = self._text(item.get("why_it_matters"), "Cần mở URL gốc để kiểm chứng.")
                    short_items.append(f"{title}: {why}")
            if short_items:
                blocks.append(f"<h4>{self._e(label)}</h4>{self._list(short_items)}")
        return "".join(blocks) if blocks else "<p>Chưa có đủ tin tức được phân loại để bổ sung luận điểm.</p>"

    def _news_card(self, item: dict[str, Any]) -> str:
        title = self._text(item.get("title"), "Chưa có tiêu đề")
        url = self._safe_url(item.get("url"))
        tone = self._text(item.get("tone"), "trung tính")
        flags = []
        flags.extend(item.get("positive_flags") or [])
        flags.extend(item.get("negative_flags") or [])
        flags.extend(item.get("catalyst_flags") or [])
        tone_class = "tone-" + tone.replace(" ", "-").lower()
        source = self._source_display(item.get("source") or item.get("type"))
        published_at = self._format_datetime(item.get("published_at"))
        classification = self._research_classification(item)
        return f"""
<article class="news-card">
  <div>
    <h3 class="news-card__title"><a href="{self._e(url)}" target="_blank" rel="noopener noreferrer">{self._e(title)}</a></h3>
    <p class="muted">{self._e(source)} · {self._e(published_at)}</p>
    <p class="{self._e(tone_class)}">Sắc thái: {self._e(tone)} · {self._e(classification)}</p>
    <p class="news-card__snippet">{self._e(self._text(item.get("snippet"), "Chưa có trích yếu"))}</p>
  </div>
  <div class="news-card__footer">
    <p class="muted">Tín hiệu liên quan: {self._e(", ".join(flags) if flags else "Cần kiểm chứng thêm")}</p>
  </div>
</article>
"""

    def _field_table(self, data: dict[str, Any]) -> str:
        if not data:
            return "<p>Chưa đủ dữ liệu xác thực</p>"
        return self._table(["Trường", "Giá trị"], [(key, self._value(value)) for key, value in data.items()])

    def _list_of_dicts_table(self, rows: Any, preferred_keys: list[str] | None = None) -> str:
        if not isinstance(rows, list) or not rows:
            return "<p>Chưa đủ dữ liệu xác thực</p>"
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
        return self._table(keys, body) if keys and body else "<p>Chưa đủ dữ liệu xác thực</p>"

    def _display_scores(self, scores: dict[str, Any]) -> dict[str, Any]:
        labels = [
            ("Định giá", "valuation_score"),
            ("Chất lượng", "quality_score"),
            ("Tăng trưởng", "growth_score"),
            ("Động lượng giá", "momentum_score"),
            ("Thanh khoản", "liquidity_score"),
            ("Quy mô", "size_score"),
            ("Rủi ro", "risk_score"),
            ("Nhãn rủi ro", "risk_label"),
            ("Điểm tổng", "overall_score"),
            ("Nhãn tổng", "overall_label"),
        ]
        display = {label: scores.get(key) for label, key in labels if key in scores}
        if "score_confidence" in scores:
            display["Tỷ lệ tin cậy dữ liệu"] = self._format_confidence(scores.get("score_confidence"))
        return display

    def _table(self, headers: list[str], rows: list[tuple[Any, ...]]) -> str:
        if not headers or not rows:
            return "<p>Chưa đủ dữ liệu xác thực</p>"
        head = "".join(f"<th>{self._e(header)}</th>" for header in headers)
        body_rows = []
        for row in rows:
            padded = list(row) + [""] * max(len(headers) - len(row), 0)
            cells = "".join(f"<td>{self._e(self._value(value))}</td>" for value in padded[: len(headers)])
            body_rows.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"

    def _with_table_class(self, table_html: str, class_name: str) -> str:
        if "<table" not in table_html:
            return table_html
        if 'class="' in table_html.split(">", 1)[0]:
            return re.sub(r'<table\s+class="([^"]*)"', f'<table class="\\1 {class_name}"', table_html, count=1)
        return table_html.replace("<table", f'<table class="{class_name}"', 1)

    def _wrap_table_scroll(self, table_html: str, extra_class: str = "") -> str:
        if "<table" not in table_html:
            return table_html
        classes = "table-scroll"
        if extra_class:
            classes += f" {extra_class}"
        return f'<div class="{classes}">{table_html}</div>'

    def _list(self, values: Any) -> str:
        items = []
        if isinstance(values, list):
            items = [self._value(item) for item in values if self._value(item) != "Chưa có dữ liệu"]
        elif isinstance(values, str) and values.strip():
            items = [values.strip()]
        if not items:
            return "<p>Chưa đủ dữ liệu xác thực</p>"
        return "<ul>" + "".join(f"<li>{self._e(item)}</li>" for item in items) + "</ul>"

    def _first_value(self, data: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    def _list_dicts(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _num(self, value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            normalized = text.lower()
            invalid_terms = ("chưa xác minh", "chưa đủ", "n/a", "na", "null", "none", "--")
            if any(term in normalized for term in invalid_terms):
                return None
            text = text.replace("\u00a0", "").replace(" ", "")
            if "," in text and "." in text:
                if text.rfind(",") > text.rfind("."):
                    text = text.replace(".", "").replace(",", ".")
                else:
                    text = text.replace(",", "")
            elif "," in text:
                parts = text.split(",")
                if len(parts[-1]) in {1, 2}:
                    text = text.replace(",", ".")
                else:
                    text = text.replace(",", "")
            try:
                numeric = float(text)
            except ValueError:
                return None
            if not (-1_000_000_000_000_000 <= numeric <= 1_000_000_000_000_000):
                return None
            return numeric
        return None

    def _score_pct(self, value: Any) -> int:
        if isinstance(value, float) and 0 <= value <= 1:
            return max(0, min(100, int(round(value * 100))))
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(value))))
        return 50

    def _polyline_points(self, values: list[float], *, width: int, height: int, padding: int) -> str:
        numeric = [float(value) for value in values if isinstance(value, (int, float))]
        if len(numeric) < 2:
            return ""
        min_value = min(numeric)
        max_value = max(numeric)
        span = max(max_value - min_value, 1)
        usable_width = width - padding * 2
        usable_height = height - padding * 2
        points = []
        for index, value in enumerate(numeric):
            x = padding + (usable_width * index / max(len(numeric) - 1, 1))
            y = padding + usable_height - ((value - min_value) / span * usable_height)
            points.append(f"{x:.1f},{y:.1f}")
        return " ".join(points)

    def _safe_url(self, value: Any) -> str:
        raw = str(value or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            return raw
        return "#"

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

    def _research_classification(self, item: dict[str, Any]) -> str:
        if item.get("negative_flags"):
            return "Rủi ro/tín hiệu tiêu cực"
        if item.get("positive_flags") or item.get("catalyst_flags"):
            return "Catalyst tích cực"
        if item.get("title"):
            return "Bối cảnh trung tính"
        return "Cần kiểm chứng"

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
        return format_percent_ratio(value)

    def _text(self, value: Any, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _e(self, value: Any) -> str:
        return html.escape(str(value), quote=True)

    def _sanitize_main_sections(self, html_document: str) -> str:
        parts = re.split(r"(?is)(<script\b.*?</script>|<style\b.*?</style>)", html_document)
        sanitized: list[str] = []
        for part in parts:
            if re.match(r"(?is)<(script|style)\b", part or ""):
                sanitized.append(part)
            else:
                sanitized.append(self._sanitize_user_facing_text(part))
        return "".join(sanitized)

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
            (r"Không gọi được watchlists[^<\n.]*", "Danh sách theo dõi cá nhân chưa được sử dụng trong báo cáo này"),
            (r"\bwatchlists\b", "danh sách theo dõi cá nhân"),
            (r"Stock chưa gắn[^<\n.]*", "Dữ liệu phân loại ngành hiện chưa đủ để lập bảng so sánh đáng tin cậy"),
            (r"API failed", "nguồn dữ liệu chưa phản hồi"),
            (r"backend_api", "nguồn dữ liệu nội bộ"),
            (r"external_financial", "nguồn tài chính công khai"),
            (r"filesystem", "file báo cáo"),
            (r"/api/[^\s<\"]+", "đường dẫn dữ liệu nội bộ"),
            (r"\bMongo\b", "cơ sở dữ liệu nội bộ"),
            (r"\bPlaywright\b", "nguồn dữ liệu công khai"),
            (r"browser rendering", "quá trình tải dữ liệu công khai"),
            (r"render bằng trình duyệt", "đối chiếu từ nguồn công khai"),
            (r"\brender\b", "tải dữ liệu"),
            (r"\bDOM\b", "nội dung trang"),
            (r"HTML tĩnh", "nội dung trang tĩnh"),
            (r"HTML Vietstock", "nội dung trang Vietstock"),
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


def build_report_chart_payload(summary: dict[str, Any]) -> dict[str, Any]:
    service = HtmlService()
    return {"charts": service._build_chart_data_payload(summary)}


def build_financial_echarts_options(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return HtmlService().build_financial_chart_data(summary)


def build_score_echarts_options(summary: dict[str, Any]) -> list[dict[str, Any]]:
    chart = HtmlService().build_score_chart_data(summary)
    return [chart] if chart else []


def build_peer_echarts_options(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return HtmlService().build_peer_chart_data(summary)
