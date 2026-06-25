import json
from pathlib import Path
import re

from analyse.config.settings import Settings
from analyse.services.html_service import HtmlService, build_report_chart_payload, normalize_market_health_score
from analyse.services.markdown_service import MarkdownService


def _summary():
    return {
        "symbol": "FPT",
        "company": "Cong ty <script>alert(1)</script>",
        "scope_exchange": "HOSE",
        "disclaimer": "Báo cáo này chỉ phục vụ tham khảo/học tập, không phải khuyến nghị đầu tư cá nhân hóa.",
        "latest_market": {"close_price": 100.0, "volume": 1000, "eps": 5000, "pe": 10.0, "pb": 2.0, "roe": 20.0},
        "financial_balance": {"roe": 20.0},
        "momentum": {"change_pct": 11.11, "period_points": 2},
        "scores": {
            "valuation_score": 75,
            "quality_score": 80,
            "growth_score": 70,
            "momentum_score": 65,
            "liquidity_score": 60,
            "size_score": 72,
            "risk_score": 45,
            "risk_label": "Trung bình",
            "overall_score": 71,
            "overall_label": "Khá tích cực",
            "score_confidence": 0.8,
            "score_explanations": ["P/E hợp lý", "Momentum tích cực"],
        },
        "score_explanations": ["P/E hợp lý", "Momentum tích cực"],
        "data_coverage": {"latest_price_loaded": True, "external_research_items": 1},
        "bctc_3q": {
            "has_bctc": True,
            "periods": [
                {"period": "Q2/2026", "revenue": 1200, "gross_profit": 400, "operating_profit": 250, "profit_after_tax": 200, "parent_profit": 190, "eps": 1000, "total_assets": 5000, "total_liabilities": 2000, "equity": 3000}
            ],
            "data_quality_notes": [],
        },
        "hose_market_context": {"vnindex": 1300, "change_percent": 0.5, "regime": "neutral", "regime_score": 75},
        "market_general_context": {
            "exchange": "HOSE",
            "primary_index": {"vnindex": 1300, "change_percent": 0.5, "regime": "risk_on", "regime_score": 75, "source": "mongo:test"},
            "source": "mongo:test",
        },
        "industry_peer_context": {
            "industry": {"sector": "Technology", "industry": "Software"},
            "peers": [{"symbol": "CMG", "company": "CMC", "pe": 12, "pb": 2, "roe": 15}],
        },
        "same_industry_recommendation": {"candidates": [{"symbol": "CMG", "company": "CMC", "roe": 15}], "method": "mock"},
        "external_research_context": {
            "enabled": True,
            "status": "success",
            "items": [
                {
            "source": "CafeF",
            "type": "google_news_rss",
                    "title": "FPT <b>lợi nhuận tăng</b>",
                    "url": "javascript:alert(1)",
                    "published_at": "2026-06-22T09:00:00+07:00",
                    "snippet": "<img src=x onerror=alert(1)>",
                    "tone": "tích cực",
                    "positive_flags": ["lợi nhuận tăng"],
                    "negative_flags": [],
                    "catalyst_flags": ["cổ tức"],
                }
            ],
            "source_statuses": [{"name": "Google News RSS", "status": "success", "items": 1}],
        },
        "system_decision": {"status": "CHƯA ĐỦ DỮ LIỆU", "action": "Cần kiểm tra thêm", "reasons": ["Dữ liệu còn mỏng"]},
        "investment_plan": {"position_sizing": {"capital_vnd": 100000000}, "action_table": []},
        "strengths": ["Có dữ liệu giá"],
        "weaknesses": ["Thiếu BCTC đầy đủ"],
    }


def _strip_code_blocks(html: str) -> str:
    return re.sub(r"(?is)<(script|style)\b.*?</\1>", "", html)


def test_markdown_renderer_contains_required_sections_and_metrics():
    markdown = MarkdownService().build(_summary(), llm_narrative="LLM narrative")

    assert "# Báo cáo phân tích cổ phiếu FPT / HOSE" in markdown
    assert "## 1. Tóm tắt điều hành" in markdown
    assert "## 11. Lộ trình theo dõi" in markdown
    assert "## 14. Phụ lục kỹ thuật và nguồn dữ liệu" in markdown
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in markdown
    assert "P/E" in markdown
    assert "Q2/2026" in markdown
    assert "CMG" in markdown
    assert "valuation_score" not in markdown.split("## 14. Phụ lục")[0]
    assert "Điểm định giá" in markdown
    assert "Tỷ lệ tin cậy dữ liệu" in markdown
    assert "80%" in markdown
    assert "CafeF" in markdown
    assert "22/06/2026 09:00" in markdown
    assert "2026-06-22T09:00:00+07:00" not in markdown.split("## 14. Phụ lục")[0]
    assert "LLM narrative" in markdown


def test_html_renderer_escapes_unsafe_text_and_urls(tmp_path):
    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build(
        "FPT_HOSE_20260622_105312",
        _summary(),
        "# Markdown <script>",
        data_sources=[{"name": "Report HTML file", "type": "filesystem", "status": "success"}],
        provider={"name": "openai", "model": "gpt-env", "status": "success"},
    )

    assert "<!doctype html>" in html
    assert '<html lang="vi">' in html
    assert "FPT" in html
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in html
    assert '<section id="cover">' in html
    assert 'id="summary-strip"' in html
    assert '<section id="executive-summary">' in html
    assert '<section id="business-overview">' in html
    assert '<section id="market-context">' in html
    assert '<section id="stock-quality-dashboard">' in html
    assert "score-card" in html
    assert "news-card__title" in html
    assert "news-card__snippet" in html
    assert "news-card__footer" in html
    assert "repeat(auto-fit, minmax(280px, 1fr))" in html
    assert "market-health-card" in html
    assert "market-cards" in html
    assert "timeline-card" in html
    assert "coverage-card" in html
    assert "Tác động có thể có" in html
    assert "valuation_score" not in html
    assert "Điểm định giá" in html
    assert "Tỷ lệ tin cậy" in html
    assert "80%" in html
    assert "Q2/2026" in html
    assert "CMG" in html
    assert "VNINDEX" in html or "vnindex" in html
    assert '<section id="external-research">' in html
    assert '<section id="strengths">' in html
    assert '<section id="weaknesses-risks">' in html
    assert '<section id="data-coverage">' in html
    assert '<section id="appendix">' not in html
    assert "22/06/2026 09:00" in html
    assert "2026-06-22T09:00:00+07:00" not in html.split('<section id="data-coverage">')[0]
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert 'href="#"' in html
    assert "javascript:alert(1)" not in html


def test_company_overview_renders_leadership_and_ownership_tables(tmp_path):
    summary = _summary()
    summary["report_presentation"] = {
        "executive_summary": {"status": "CÓ THỂ THEO DÕI", "main_thesis": "Theo dõi có điều kiện."},
        "business_overview": {
            "company_name": "Ngân hàng TMCP Ví dụ",
            "exchange": "HOSE",
            "description": "Ngân hàng TMCP Ví dụ được đối chiếu từ CafeF thông tin doanh nghiệp.",
            "business_overview": "Dịch vụ ngân hàng thương mại.",
            "industry": {"industry_group": "Tổ chức tín dụng", "industry": "Ngân hàng", "source": "CafeF thông tin doanh nghiệp"},
            "leadership": [{"name": "Nguyễn Văn A", "position": "Chủ tịch HĐQT", "shares": "1,000", "ownership_percent": "0.01%", "source": "CafeF thông tin doanh nghiệp"}],
            "ownership": [{"holder": "Cổ đông Nhà nước", "shares": "1,000,000", "ownership_percent": "50%", "source": "CafeF thông tin doanh nghiệp"}],
            "drivers": ["Tăng trưởng tín dụng và chất lượng tài sản."],
            "source_note": "Nguồn đối chiếu: CafeF thông tin doanh nghiệp.",
        },
        "market_context": "Bối cảnh thị trường cần được đối chiếu thêm.",
        "market_context_view": {},
        "price_momentum": "Chuỗi giá cần được đối chiếu thêm.",
        "financial_analysis": "Bộ dữ liệu BCTC hiện chưa đủ để phân tích sâu.",
        "valuation": "Chưa đủ dữ liệu định giá xác thực.",
        "peer_note": "Chưa đủ dữ liệu peer.",
        "reference_candidates": [],
        "research_insights": {},
        "score_cards": [],
        "roadmap": [],
        "data_quality": {"user_notes": [], "technical_notes": []},
        "summary_bar": {},
    }

    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build("report", summary)
    markdown = MarkdownService().build(summary)

    assert "Tổng quan doanh nghiệp</h2>" in html
    assert "Tổng quan doanh nghiệp và ngành" not in html
    assert "Ban lãnh đạo" in html
    assert "Nguyễn Văn A" in html
    assert "Sở hữu / cổ đông lớn" in html
    assert "Cổ đông Nhà nước" in html
    assert "## 2. Tổng quan doanh nghiệp" in markdown
    assert "Nguyễn Văn A" in markdown
    assert "Cổ đông Nhà nước" in markdown


def test_html_financial_chart_series_uses_available_ratio_metrics(tmp_path):
    service = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path)))
    periods = [
        {"period": "2025", "roe": 11.78, "pe": 13.2, "eps_ttm": 3000},
        {"period": "2024", "roe": 10.49, "pe": 15.43, "eps_ttm": 2600},
        {"period": "2023", "roe": 6.65, "pe": 25.0, "eps_ttm": 1800},
    ]

    series = service.build_financial_chart_series(periods)
    chart = service._financial_trend_chart(periods)

    assert "roe" in series
    assert "pe" in series
    assert "eps_ttm" in series
    assert "Xu hướng ROE" in chart
    assert "Chưa đủ kỳ có số liệu để dựng biểu đồ tài chính" not in chart


def test_html_uses_local_echarts_asset_when_available(tmp_path):
    source_asset = tmp_path / "echarts.min.js"
    source_asset.write_text("window.echarts={init:function(){return{setOption:function(){},resize:function(){}}}};", encoding="utf-8")
    report_dir = tmp_path / "reports"
    settings = Settings(
        REPORT_OUTPUT_DIR=str(report_dir),
        REPORT_CHART_ENGINE="echarts",
        REPORT_CHART_ASSET_DIR=str(report_dir / "assets"),
        REPORT_ECHARTS_LOCAL_FILE=str(source_asset),
    )
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {"period": "Q2/2026", "revenue": 1200, "gross_profit": 400, "profit_before_tax": 260, "profit_after_tax": 210, "total_assets": 5000, "equity": 3000, "roe": 20, "pe": 10, "pb": 2},
        {"period": "Q1/2026", "revenue": 1000, "gross_profit": 350, "profit_before_tax": 240, "profit_after_tax": 180, "total_assets": 4800, "equity": 2900, "roe": 18, "pe": 11, "pb": 2.1},
        {"period": "Q4/2025", "revenue": 950, "gross_profit": 330, "profit_before_tax": 210, "profit_after_tax": 160, "total_assets": 4600, "equity": 2750, "roe": 16, "pe": 12, "pb": 2.2},
    ]
    summary["price_history"] = [
        {"time": "2026-06-01", "close": 90, "volume": 1000},
        {"time": "2026-06-10", "close": 95, "volume": 1100},
        {"time": "2026-06-22", "close": 100, "volume": 1200},
    ]

    html = HtmlService(settings).build("report", summary)

    assert (report_dir / "assets" / "echarts.min.js").exists()
    assert '<script src="assets/echarts.min.js"></script>' in html
    assert 'type="application/json" id="chart-data-report"' in html
    assert 'type="application/json" id="chart-data"' in html
    chart_json = re.search(r'<script type="application/json" id="chart-data-report">(.*?)</script>', html, flags=re.DOTALL)
    assert chart_json is not None
    parsed = json.loads(chart_json.group(1))
    assert parsed["charts"]
    assert 'id="chart-financial-profit-trend"' in html
    assert 'id="chart-score-dashboard"' in html
    assert 'id="chart-price-close-trend"' in html
    assert 'data-chart-id="financial-profit-trend"' in html
    assert "document.addEventListener('DOMContentLoaded', initCharts)" in html
    assert "window.echarts.init" in html
    assert "ResizeObserver" in html
    assert "Không tải được thư viện biểu đồ cục bộ. Báo cáo vẫn hiển thị bảng số liệu." in html
    assert "Dữ liệu biểu đồ chưa sẵn sàng trong lần xuất báo cáo này." in html
    assert "Chưa đủ dữ liệu để dựng biểu đồ này." in html
    assert "const payload" not in html
    assert "const gói dữ liệu" not in html
    assert "height: 320px" in html
    assert "word-break: normal" in html
    assert "https://cdn" not in html


def test_html_missing_echarts_asset_falls_back_to_inline_svg(tmp_path):
    report_dir = tmp_path / "reports"
    settings = Settings(
        REPORT_OUTPUT_DIR=str(report_dir),
        REPORT_CHART_ENGINE="echarts",
        REPORT_CHART_ASSET_DIR=str(report_dir / "assets"),
        REPORT_ECHARTS_LOCAL_FILE=str(tmp_path / "missing-echarts.min.js"),
        REPORT_CHART_FALLBACK="inline_svg",
    )

    html = HtmlService(settings).build("report", _summary())

    assert "chart-data-report" not in html
    assert "echarts.init" not in html
    assert "chart-panel" in html
    assert "Đường giá tham khảo" in html
    assert "Đang chuẩn bị biểu đồ..." not in html


def test_market_gauge_is_replaced_by_segmented_health_bar_by_default(tmp_path):
    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path), REPORT_CHART_ENGINE="echarts")).build("report", _summary())
    market_section = html.split('<section id="market-context">', 1)[1].split("</section>", 1)[0]

    assert "Thước đo sức khỏe thị trường" in market_section
    assert "market-health-card" in market_section
    assert "75/100" in market_section
    assert "Tích cực" in market_section
    assert "0 là thận trọng hơn, 100 là tích cực hơn." in market_section
    assert "Thước đo trạng thái thị trường" not in market_section
    assert "market-regime-score" not in html
    assert "chartType\":\"gauge\"" not in html
    assert "Đang chuẩn bị biểu đồ..." not in market_section


def test_market_health_missing_score_renders_clean_empty_state(tmp_path):
    summary = _summary()
    summary["hose_market_context"].pop("regime_score", None)
    summary["market_general_context"]["primary_index"].pop("regime_score", None)

    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build("report", summary)
    market_section = html.split('<section id="market-context">', 1)[1].split("</section>", 1)[0]

    assert "Thước đo sức khỏe thị trường" in market_section
    assert "Chưa đủ dữ liệu để dựng thước đo sức khỏe thị trường." in market_section
    assert "Đang chuẩn bị biểu đồ..." not in market_section


def test_market_health_score_direction_is_consistent():
    assert normalize_market_health_score(75) == 75
    assert normalize_market_health_score(25, "higher_is_risk") == 75
    assert normalize_market_health_score("Chưa xác minh") is None


def test_market_health_echarts_bar_is_explicit_opt_in(tmp_path):
    source_asset = tmp_path / "echarts.min.js"
    source_asset.write_text("window.echarts={init:function(){return{setOption:function(){},resize:function(){}}}};", encoding="utf-8")
    report_dir = tmp_path / "reports"
    settings = Settings(
        REPORT_OUTPUT_DIR=str(report_dir),
        REPORT_CHART_ENGINE="echarts",
        REPORT_MARKET_CHART_TYPE="echarts_bar",
        REPORT_CHART_ASSET_DIR=str(report_dir / "assets"),
        REPORT_ECHARTS_LOCAL_FILE=str(source_asset),
    )

    html = HtmlService(settings).build("report", _summary())

    assert "market-health-score" in html
    assert "Thước đo sức khỏe thị trường" in html
    assert "Thước đo trạng thái thị trường" not in html
    assert "chartType\":\"gauge\"" not in html


def test_chart_debug_artifacts_are_written_when_debug_enabled(tmp_path):
    source_asset = tmp_path / "echarts.min.js"
    source_asset.write_text("window.echarts={init:function(){return{setOption:function(){},resize:function(){}}}};", encoding="utf-8")
    report_dir = tmp_path / "reports"
    settings = Settings(
        REPORT_OUTPUT_DIR=str(report_dir),
        REPORT_CHART_ENGINE="echarts",
        REPORT_CHART_ASSET_DIR=str(report_dir / "assets"),
        REPORT_ECHARTS_LOCAL_FILE=str(source_asset),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
    )
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {"period": "Q2/2026", "revenue": 1200, "profit_after_tax": 210, "total_assets": 5000, "equity": 3000},
        {"period": "Q1/2026", "revenue": 1000, "profit_after_tax": 180, "total_assets": 4800, "equity": 2900},
    ]

    HtmlService(settings).build("report", summary)

    payload_path = report_dir / "debug" / "FPT_chart_payload.json"
    asset_path = report_dir / "debug" / "FPT_chart_asset_check.json"
    assert payload_path.exists()
    assert asset_path.exists()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    asset = json.loads(asset_path.read_text(encoding="utf-8"))
    assert payload["chart_ids"]
    assert asset["selected_chart_engine"] == "echarts"
    assert asset["script_src_used_in_html"] == "assets/echarts.min.js"
    assert asset["local_asset_exists"] is True


def test_echarts_financial_chart_data_sorts_periods_and_filters_suspicious_bank_values(tmp_path):
    service = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path), REPORT_CHART_ENGINE="echarts"))
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {
            "period": "Q1/2026",
            "net_interest_income": 20000,
            "profit_before_tax": 12000,
            "profit_after_tax": 9000,
            "total_assets": 0.38,
            "customer_loans": 1500000,
            "customer_deposits": 1600000,
            "equity": 2550963,
            "roe": 18.2,
        },
        {
            "period": "Q4/2025",
            "net_interest_income": 19000,
            "profit_before_tax": 11000,
            "profit_after_tax": 8500,
            "total_assets": 0.36,
            "customer_loans": 1420000,
            "customer_deposits": 1520000,
            "equity": 2450000,
            "roe": 17.8,
        },
    ]

    charts = service.build_financial_chart_data(summary)
    profit_chart = next(chart for chart in charts if chart["id"] == "financial-profit-trend")
    balance_chart = next(chart for chart in charts if chart["id"] == "financial-balance-scale")

    assert profit_chart["x"] == ["Q4/2025", "Q1/2026"]
    assert "Tổng tài sản" not in [series["name"] for series in balance_chart["series"]]
    for series in balance_chart["series"]:
        assert 0.38 not in series["values"]
        assert 0.36 not in series["values"]


def test_chart_payload_builder_uses_only_valid_numeric_values(tmp_path):
    service = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path), REPORT_CHART_ENGINE="echarts"))
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {"period": "Q2/2026", "revenue": "1,200", "profit_after_tax": "Chưa xác minh", "total_assets": "5,000", "equity": "3,000"},
        {"period": "Q1/2026", "revenue": "1,000", "profit_after_tax": "", "total_assets": "4,800", "equity": "2,900"},
    ]

    charts = service.build_financial_chart_data(summary)
    payload = build_report_chart_payload(summary)
    profit_chart = next(chart for chart in charts if chart["id"] == "financial-profit-trend")

    revenue_series = next(series for series in profit_chart["series"] if series["name"] == "Doanh thu")
    assert revenue_series["values"] == [1000.0, 1200.0]
    assert "LNST" not in [series["name"] for series in profit_chart["series"]]
    json.dumps(payload, ensure_ascii=False)


def test_chart_builder_returns_no_trend_chart_when_only_one_valid_point(tmp_path):
    service = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path), REPORT_CHART_ENGINE="echarts"))
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {"period": "Q2/2026", "revenue": 1200, "profit_after_tax": 210},
        {"period": "Q1/2026", "revenue": "Chưa xác minh", "profit_after_tax": None},
    ]

    charts = service.build_financial_chart_data(summary)

    assert not any(chart["id"] == "financial-profit-trend" for chart in charts)


def test_echarts_financial_table_stays_above_charts(tmp_path):
    source_asset = tmp_path / "echarts.min.js"
    source_asset.write_text("window.echarts={init:function(){return{setOption:function(){},resize:function(){}}}};", encoding="utf-8")
    report_dir = tmp_path / "reports"
    settings = Settings(
        REPORT_OUTPUT_DIR=str(report_dir),
        REPORT_CHART_ENGINE="echarts",
        REPORT_CHART_ASSET_DIR=str(report_dir / "assets"),
        REPORT_ECHARTS_LOCAL_FILE=str(source_asset),
    )
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {"period": "Q2/2026", "revenue": 1200, "profit_before_tax": 260, "profit_after_tax": 210, "total_assets": 5000, "equity": 3000},
        {"period": "Q1/2026", "revenue": 1000, "profit_before_tax": 240, "profit_after_tax": 180, "total_assets": 4800, "equity": 2900},
    ]

    html = HtmlService(settings).build("report", summary)
    financial_section = html.split('<section id="financial-statement-analysis">', 1)[1].split("</section>", 1)[0]

    assert 'class="table-scroll financial-table-scroll"' in financial_section
    assert "chart-grid chart-grid--two" in financial_section
    assert financial_section.index("financial-table-scroll") < financial_section.index("chart-grid chart-grid--two")


def test_html_financial_one_period_renders_metric_cards(tmp_path):
    service = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path)))
    periods = [{"period": "2025", "roe": 11.78, "pe": 13.2}]

    chart = service._financial_trend_chart(periods)

    assert "Chỉ tiêu tài chính kỳ gần nhất" in chart
    assert "Xu hướng ROE" not in chart


def test_html_financial_section_uses_scroll_table_and_chart_grid(tmp_path):
    summary = _summary()
    summary["bctc_3q"]["periods"] = [
        {
            "period": "Q1/2026",
            "net_interest_income": 20000,
            "profit_after_tax": 9000,
            "total_assets": 0.38,
            "customer_loans": 1500000,
            "customer_deposits": 1600000,
            "equity": 2550963,
            "roa": 0.38,
            "roe": 18.2,
        },
        {
            "period": "Q4/2025",
            "net_interest_income": 19000,
            "profit_after_tax": 8500,
            "total_assets": 0.36,
            "customer_loans": 1420000,
            "customer_deposits": 1520000,
            "equity": 2450000,
            "roa": 0.36,
            "roe": 17.8,
        },
    ]
    summary["financial_balance"] = summary["bctc_3q"]["periods"][0]

    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path), REPORT_CHART_ENGINE="inline_svg")).build("report", summary)
    financial_section = html.split('<section id="financial-statement-analysis">', 1)[1].split("</section>", 1)[0]

    assert 'class="table-scroll financial-table-scroll"' in financial_section
    assert "financial-charts-grid" in financial_section
    assert "financial-grid" not in html
    assert "Xu hướng tổng tài sản" not in financial_section
    assert ">0.38<" not in financial_section.split("ROA", 1)[0]
    assert "Hàng tồn kho" not in financial_section


def test_html_peer_section_renders_qualitative_cards(tmp_path):
    summary = _summary()
    summary["industry_peer_context"] = {
        "industry": {"sector": "Tài chính", "industry_group": "Tổ chức tín dụng", "industry": "Ngân hàng", "source": "Vietstock Finance"},
        "peers": [
            {"symbol": "BID", "company": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam", "source_url": "https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", "verified_row_evidence": "stock_link"},
            {"symbol": "CTG", "company": "Ngân hàng TMCP Công Thương Việt Nam", "source_url": "https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", "verified_row_evidence": "stock_link"},
        ],
    }

    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build("report", summary)

    assert "peer-card-grid" in html
    assert "BID" in html
    assert "Cần chờ xác nhận" in html
    assert "Ngành cấp cao" in html
    assert "Tổ chức tín dụng" in html


def test_source_status_peer_zero_is_not_misleading(tmp_path):
    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build(
        "report",
        _summary(),
        data_sources=[
            {
                "name": "Vietstock peer cùng ngành",
                "status": "insufficient",
                "detail": "https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm; page_loaded=true; tables_found=0; grid_rows_found=0; peer_rows_found=0; normalized_peers=0",
            }
        ],
    )

    assert "Chưa đủ dữ liệu" in html
    assert "Nguồn đã được kiểm tra nhưng chưa đủ dòng peer cùng ngành dùng được" in html


def test_cafef_company_source_status_uses_specific_user_facing_name(tmp_path):
    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build(
        "report",
        _summary(),
        data_sources=[
            {
                "name": "CafeF thông tin doanh nghiệp",
                "type": "external_company",
                "status": "insufficient",
                "detail": "Nguồn thông tin doanh nghiệp; https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn; fields=0; leadership_rows=0; ownership_rows=0",
            }
        ],
    )

    assert "CafeF thông tin doanh nghiệp" in html
    assert "Chưa đủ dữ liệu" in html
    assert "CafeF đã được kiểm tra nhưng chưa đủ hồ sơ doanh nghiệp" in html


def test_technical_warnings_are_kept_out_of_main_report_sections(tmp_path):
    summary = _summary()
    technical = [
        "Field thiếu từ Backend: financials.periods, industry, industryPeerContext.peers",
        "Không gọi được watchlists do thiếu/sai token",
        "Stock chưa gắn industry_id nên không thể dựng peer context đầy đủ.",
        "Playwright rendering failed: TimeoutError: selector not found trong HTML DOM.",
    ]
    summary["data_quality_notes"] = [
        "Dữ liệu so sánh ngành hiện chưa đủ để đưa ra đánh giá tương quan đáng tin cậy.",
        "Danh sách theo dõi cá nhân chưa được sử dụng trong báo cáo này.",
    ]
    summary["technical_data_quality_notes"] = technical
    summary["report_presentation"] = {
        "executive_summary": {
            "status": "CHƯA ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN",
            "main_thesis": "Cần bổ sung BCTC và peer trước khi kết luận mạnh.",
            "key_positives": ["Có dữ liệu giá và thanh khoản."],
            "key_risks": ["Dữ liệu so sánh ngành hiện chưa đủ để đưa ra đánh giá tương quan đáng tin cậy."],
            "confidence": 0.45,
            "confidence_label": "Thấp",
            "checks_before_action": ["Đối chiếu nguồn dữ liệu gốc."],
        },
        "business_overview": {"description": "Chưa đủ dữ liệu xác thực để mô tả mô hình kinh doanh.", "drivers": []},
        "market_context": "Bối cảnh thị trường cần được đối chiếu thêm.",
        "price_momentum": "Chuỗi giá hiện có thể dùng để tham khảo xu hướng.",
        "financial_analysis": "Bộ dữ liệu BCTC hiện chưa đủ để phân tích sâu.",
        "valuation": "Chưa đủ dữ liệu định giá xác thực.",
        "peer_note": "Chưa có bảng peer định lượng đủ sạch trong lần chạy này; báo cáo không tự tạo số liệu khi nguồn công khai chưa xác nhận.",
        "reference_candidates": [],
        "research_insights": {},
        "score_cards": [],
        "roadmap": [{"phase": "Theo dõi ngắn hạn", "horizon": "1-2 tuần", "focus": "Theo dõi giá và thanh khoản."}],
        "data_quality": {"user_notes": summary["data_quality_notes"], "technical_notes": technical},
        "summary_bar": {"latest_price": 100, "overall_score": 71, "risk_label": "Trung bình", "financial_periods_count": 1, "data_confidence": 0.45},
    }

    markdown = MarkdownService().build(summary)
    markdown_main = markdown.split("## 14. Phụ lục")[0]
    forbidden = [
        "Backend",
        "Service",
        "payload",
        "field",
        "model",
        "metadata",
        "industry_id",
        "industryPeerContext",
        "financials.periods",
        "factFinancialStatements",
        "watchlists token",
        "backend_api",
        "missing_fields",
        "primary_index",
        "index_symbol",
        "time_id",
        "updated_at",
        "change_percent",
        "total_value",
        "source_status",
        "provider",
        "latency_ms",
        "filesystem",
        "external_financial",
        "API failed",
        "Playwright",
        "BCTT",
        "NotImplementedError",
        "HTML",
        "DOM",
        "selector",
        "Field thiếu từ Backend",
        "Không gọi được watchlists",
        "Stock chưa gắn industry_id",
    ]
    for term in forbidden:
        assert term not in markdown_main
    assert "Dữ liệu so sánh ngành hiện chưa đủ" in markdown_main
    assert "Field thiếu từ Backend" not in markdown
    assert "Playwright rendering failed" not in markdown

    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build("report", summary, markdown)
    html_user = _strip_code_blocks(html)
    for term in forbidden:
        assert term not in html_user
    assert "Dữ liệu so sánh ngành hiện chưa đủ" in html_user
    assert "Field thiếu từ Backend" not in html_user
    assert "Playwright rendering failed" not in html_user


def test_renderers_format_confidence_as_percent_and_hide_bctt(tmp_path):
    summary = _summary()
    summary["scores"]["score_confidence"] = 0.6
    summary["report_presentation"] = {
        "executive_summary": {
            "status": "CÓ THỂ THEO DÕI",
            "main_thesis": "Dữ liệu hiện tại đủ để lập khung theo dõi.",
            "confidence": 0.6,
            "confidence_label": "Trung bình",
        },
        "summary_bar": {"latest_price": 100, "overall_score": 71, "risk_label": "Trung bình", "financial_periods_count": 1, "data_confidence": 0.6},
        "score_cards": [
            {"key": "data_confidence", "label": "Tỷ lệ tin cậy dữ liệu", "score": 0.6, "score_label": "Trung bình", "reason": "Đủ dữ liệu giá nhưng peer còn thiếu.", "data_used": "Độ phủ dữ liệu."}
        ],
        "reference_candidates": [
            {
                "ticker": "CMG",
                "company": "CMC",
                "reason_to_watch": "Cùng nhóm công nghệ theo nguồn so sánh.",
                "supporting_data": {"pe": 12, "pb": 2, "roe": 15},
                "key_risk": "Cần đối chiếu quy mô.",
                "missing_data": "",
                "confidence": 0.75,
                "source": "Vietstock Finance BCTT",
            }
        ],
    }

    markdown = MarkdownService().build(summary)
    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path))).build(
        "report",
        summary,
        markdown,
        data_sources=[{"name": "Vietstock Finance BCTT", "status": "partial", "type": "external_financial"}],
    )

    assert "Tỷ lệ tin cậy" in markdown
    assert "60%" in markdown
    assert "75%" in markdown
    assert "BCTT" not in markdown
    assert "Tỷ lệ tin cậy" in html
    assert "60%" in html
    assert "75%" in html
    assert "Vietstock Finance BCTC" in html
    assert "Ghi nhận một phần" in html
    assert "BCTT" not in html
