from analyse.config.settings import Settings
from analyse.services.html_service import HtmlService
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
        "hose_market_context": {"vnindex": 1300, "change_percent": 0.5, "regime": "neutral"},
        "market_general_context": {"exchange": "HOSE", "primary_index": {"vnindex": 1300}, "source": "mongo:test"},
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


def test_markdown_renderer_contains_required_sections_and_metrics():
    markdown = MarkdownService().build(_summary(), llm_narrative="LLM narrative")

    assert "# Báo cáo phân tích cổ phiếu FPT trên HOSE" in markdown
    assert "## 14. Từ điển chỉ số, đơn vị và cách đọc" in markdown
    assert "Báo cáo này chỉ phục vụ tham khảo/học tập" in markdown
    assert "P/E" in markdown
    assert "Q2/2026" in markdown
    assert "CMG" in markdown
    assert "valuation_score" in markdown
    assert "CafeF" in markdown
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
    assert '<section id="executive-summary">' in html
    assert '<section id="market-context">' in html
    assert '<section id="stock-quality-dashboard">' in html
    assert "valuation_score" in html
    assert "Q2/2026" in html
    assert "CMG" in html
    assert "VNINDEX" in html or "vnindex" in html
    assert '<section id="external-research">' in html
    assert '<section id="strengths">' in html
    assert '<section id="weaknesses-risks">' in html
    assert '<section id="data-coverage">' in html
    assert '<section id="appendix">' in html
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert 'href="#"' in html
    assert "javascript:alert(1)" not in html
