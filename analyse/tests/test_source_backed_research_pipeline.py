import asyncio
import json

from analyse.config.settings import Settings
from analyse.research.article_extractor import ArticleExtractor
from analyse.research.evidence_normalizer import EvidenceNormalizer
from analyse.research.research_query_builder import ResearchQueryBuilder
from analyse.research.source_backed_enrichment_service import SourceBackedEnrichmentService
from analyse.research.source_quality import SourceQualityScorer
from analyse.schemas.research import ExternalResearchContext, ResearchItem
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.services.report_presentation_normalizer import ReportPresentationNormalizer
from analyse.services.report_service import ReportService


def _settings(**overrides):
    values = {
        "_env_file": None,
        "ENABLE_SOURCE_BACKED_RESEARCH": True,
        "ENABLE_DEEP_RESEARCH_CRAWL": False,
        "EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON": False,
        "VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON": False,
        "SOURCE_BACKED_RESEARCH_MAX_ARTICLES": 12,
    }
    values.update(overrides)
    return Settings(**values)


def _summary():
    return {
        "symbol": "FPT",
        "scope_exchange": "HOSE",
        "company": "CTCP FPT",
        "latest_market": {"close_price": 110, "volume": 1_200_000, "pe": 18, "pb": 3.2, "roe": 22},
        "momentum": {"chart_period_change_pct": 7.5, "chart_points": 60},
        "hose_market_context": {"market_health_score": 65, "status": "Khá tích cực", "trading_value_billion": 30_989.0},
        "scores": {"overall_score": 71, "risk_score": 42, "score_confidence": 0.72, "overall_label": "Tích cực", "risk_label": "Trung bình"},
        "bctc_3q": {
            "source": "Vietstock Finance BCTC",
            "periods": [
                {"period": "Q1/2026", "revenue": 1200, "profit_after_tax": 200, "total_assets": 5000, "equity": 2900, "eps": 1000, "roe": 18, "roa": 7},
                {"period": "Q4/2025", "revenue": 1100, "profit_after_tax": 180, "total_assets": 4800, "equity": 2800, "eps": 900, "roe": 17, "roa": 6.8},
                {"period": "Q3/2025", "revenue": 1000, "profit_after_tax": 160, "total_assets": 4600, "equity": 2700, "eps": 850, "roe": 16, "roa": 6.5},
            ],
        },
        "company_overview": {
            "source_display": "CafeF thông tin doanh nghiệp",
            "source_url": "https://cafef.vn/du-lieu/hose/fpt-ban-lanh-dao-so-huu.chn",
            "company_name": "CTCP FPT",
            "industry": "Công nghệ",
            "leadership": [{"name": "Nguyễn Văn A"}],
            "ownership": [{"name": "Cổ đông B", "ownership_percent": 5.2}],
        },
        "industry_peer_context": {"peers": [{"symbol": "CMG"}, {"symbol": "ELC"}, {"symbol": "CTR"}]},
        "data_coverage": {
            "financial_periods_count": 3,
            "price_history_points": 60,
            "latest_price_loaded": True,
            "market_context_loaded": True,
            "watchlist_loaded": True,
            "external_research_items": 1,
        },
        "weaknesses": ["Rủi ro thị trường chung nếu VN-Index chuyển trạng thái phòng thủ."],
    }


def _research_context():
    return ExternalResearchContext(
        enabled=True,
        status="success",
        items=[
            ResearchItem(
                source="Vietstock",
                type="vietstock_via_google_news_rss",
                title="FPT công bố kết quả kinh doanh tăng trưởng",
                url="https://vietstock.vn/fpt-ket-qua-kinh-doanh.htm",
                published_at="2026-06-10T00:00:00+00:00",
                snippet="FPT ghi nhận kết quả kinh doanh tích cực và triển vọng chuyển đổi số.",
                tone="tích cực",
                relevance_score=0.9,
                positive_flags=["tăng trưởng"],
                catalyst_flags=["kết quả kinh doanh"],
            )
        ],
    )


def test_research_query_builder_generates_vietnamese_source_specific_queries():
    queries = ResearchQueryBuilder(_settings()).build_queries(
        symbol="FPT",
        company_name="CTCP FPT",
        exchange="HOSE",
        domains=["vietstock.vn"],
        max_queries=20,
    )

    assert any("FPT cổ phiếu" in query for query in queries)
    assert any("kết quả kinh doanh" in query for query in queries)
    assert any("báo cáo tài chính" in query for query in queries)
    assert any("triển vọng" in query for query in queries)
    assert any("site:vietstock.vn" in query for query in queries)


def test_evidence_normalizer_preserves_source_url_date_and_facts():
    evidence = EvidenceNormalizer().from_research_item(
        _research_context().items[0],
        symbol="FPT",
        exchange="HOSE",
        company_name="CTCP FPT",
    )

    assert evidence.source_name == "Vietstock"
    assert evidence.url == "https://vietstock.vn/fpt-ket-qua-kinh-doanh.htm"
    assert evidence.published_at is not None
    assert evidence.extracted_facts[0].source_url == evidence.url
    assert evidence.extracted_facts[0].key == "news_tone"


def test_source_quality_scorer_ranks_backend_vietstock_cafef_above_generic():
    scorer = SourceQualityScorer()

    backend = scorer.reliability_score(source_name="Dữ liệu giá và thanh khoản", source_type="backend")
    vietstock = scorer.reliability_score(source_name="Vietstock", source_type="news", url="https://news.google.com/rss/articles/x")
    cafef = scorer.reliability_score(source_name="CafeF", source_type="news", url="https://news.google.com/rss/articles/y")
    generic = scorer.reliability_score(source_name="Blog", source_type="news", url="https://example.com/a")

    assert backend > vietstock > generic
    assert backend > cafef > generic


def test_article_extractor_removes_script_nav_and_footer_noise():
    html = """
    <html><head><title>FPT tăng trưởng - Site</title><script>secret()</script></head>
    <body><nav>Trang chủ Menu Đăng nhập</nav><h1>FPT tăng trưởng lợi nhuận</h1>
    <p>FPT ghi nhận động lực chuyển đổi số và đơn hàng mới trong kỳ gần nhất.</p>
    <footer>Liên hệ Facebook Zalo</footer></body></html>
    """
    extracted = ArticleExtractor(_settings()).extract(html, url="https://vietstock.vn/fpt.htm")

    assert extracted["title"] == "FPT tăng trưởng lợi nhuận"
    assert "secret" not in extracted["body_text"]
    assert "Trang chủ" not in extracted["body_text"]
    assert "Facebook" not in extracted["body_text"]
    assert "chuyển đổi số" in extracted["body_text"]


def test_evidence_deduplicates_duplicate_urls():
    normalizer = EvidenceNormalizer()
    item_a = _research_context().items[0]
    item_b = item_a.model_copy(update={"title": "FPT tin cập nhật khác"})
    evidence = [
        normalizer.from_research_item(item_a, symbol="FPT", exchange="HOSE", company_name="CTCP FPT"),
        normalizer.from_research_item(item_b, symbol="FPT", exchange="HOSE", company_name="CTCP FPT"),
    ]

    accepted, rejected = normalizer.dedupe_and_score(evidence, symbol="FPT", company_name="CTCP FPT")

    assert len(accepted) == 1
    assert len(rejected) == 1
    assert "duplicate_evidence" in rejected[0].warnings


def test_forecast_scenario_generator_produces_three_probability_scenarios():
    service = SourceBackedEnrichmentService(_settings())
    enriched = asyncio.run(
        service.enrich(
            symbol="FPT",
            exchange="HOSE",
            company_name="CTCP FPT",
            summary=_summary(),
            research_context=_research_context(),
        )
    )

    scenarios = enriched["forecast_scenarios"]
    assert [row["scenario"] for row in scenarios] == ["Tích cực", "Cơ sở", "Thận trọng"]
    assert sum(row["probability_pct"] for row in scenarios) == 100
    assert all(row["condition"] for row in scenarios)
    assert all(row["invalidation_signals"] for row in scenarios)
    assert all("khuyến nghị" in row["risk_note"] for row in scenarios)


def test_action_plan_and_checklist_are_safe_and_useful_when_evidence_exists():
    service = SourceBackedEnrichmentService(_settings())
    enriched = asyncio.run(
        service.enrich(
            symbol="FPT",
            exchange="HOSE",
            company_name="CTCP FPT",
            summary=_summary(),
            research_context=_research_context(),
        )
    )

    rows = enriched["action_plan"]["watch_points"]
    checklist = enriched["checklist"]
    text = json.dumps({"rows": rows, "checklist": checklist}, ensure_ascii=False).lower()

    assert rows
    assert checklist
    assert "chưa xác minh" not in text
    assert "mua ngay" not in text
    assert "bán ngay" not in text
    assert "vùng giá hiện tại" in text
    assert "tín hiệu vô hiệu" in text


def test_numeric_facts_without_source_are_not_fabricated():
    evidence = EvidenceNormalizer().from_summary(
        symbol="FPT",
        exchange="HOSE",
        company_name="CTCP FPT",
        summary={"scores": {"overall_score": 50}, "latest_market": {}, "bctc_3q": {"periods": []}},
        research_context=ExternalResearchContext(enabled=True, status="success", items=[]),
    )
    fact_keys = {fact.key for item in evidence for fact in item.extracted_facts}

    assert "close_price" not in fact_keys
    assert "revenue" not in fact_keys
    assert "target_price" not in fact_keys


def test_presentation_scenario_table_keeps_probability_and_invalidation_fields():
    normalizer = ReportPresentationNormalizer(settings=_settings())
    summary = _summary()
    summary["forecast_scenarios"] = [
        {
            "scenario": "Tích cực",
            "probability_pct": 30,
            "time_horizon": "1-3 tháng",
            "condition": "Giá giữ động lượng.",
            "expected_behavior": "Tín hiệu được củng cố.",
            "supporting_signals": ["Điểm tổng 71/100"],
            "invalidation_signals": ["Giá giảm mạnh kèm thanh khoản cao."],
            "risk_note": "Không phải khuyến nghị mua/bán.",
        }
    ]
    presentation = normalizer.normalize(summary, {})
    row = presentation["scenario_table"]["rows"][0]

    assert row["probability_pct"] == 30
    assert row["time_horizon"] == "1-3 tháng"
    assert row["invalidation_signals"] == ["Giá giảm mạnh kèm thanh khoản cao."]


def test_data_coverage_never_pairs_available_with_unverified_value():
    presentation = ReportPresentationNormalizer(settings=_settings()).normalize(_summary(), {})

    assert not any(
        item["status"] == "available" and item["value"] == "Chưa xác minh"
        for item in presentation["data_coverage"]["items"]
    )


def test_user_facing_source_names_are_specific_and_include_evidence_count():
    sanitized = sanitize_data_source_statuses(
        [
            {"name": "CafeF", "type": "external_company", "status": "success", "detail": "fields=5; leadership_rows=2"},
            {"name": "CafeF", "type": "external_financial", "status": "success", "detail": "periods=4"},
            {"name": "Vietstock", "type": "external_financial", "status": "success", "detail": "periods=8"},
            {"name": "Vietstock", "type": "external_peer", "status": "success", "detail": "normalized_peers=9"},
        ]
    )
    names = {item["name"] for item in sanitized}

    assert "CafeF thông tin doanh nghiệp" in names
    assert "CafeF tài chính" in names
    assert "Vietstock Finance BCTC" in names
    assert "Vietstock peer cùng ngành" in names


def test_report_status_is_not_failed_when_only_optional_source_or_history_fails():
    service = ReportService(settings=_settings())

    status = service._derive_report_status(
        analysis_status="success",
        history_status="failed",
        source_status="partial",
        warnings=["Nguồn ngoài lỗi timeout"],
        has_report_content=True,
    )

    assert status == "success_with_warnings"


def test_api_response_envelope_remains_code_message_data():
    from analyse.schemas.common import api_success

    payload = api_success("ok", data={"symbol": "FPT"})

    assert set(payload) == {"code", "message", "data"}


def test_source_backed_debug_artifacts_are_scrubbed(tmp_path):
    settings = _settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
    )
    context = ExternalResearchContext(
        enabled=True,
        status="success",
        items=[
            ResearchItem(
                source="Vietstock",
                type="vietstock_via_google_news_rss",
                title="FPT kết quả kinh doanh",
                url="https://vietstock.vn/fpt.htm",
                snippet="password=REDACTME123 api-key=REDACTME456",
                relevance_score=0.9,
            )
        ],
    )
    asyncio.run(
        SourceBackedEnrichmentService(settings).enrich(
            symbol="FPT",
            exchange="HOSE",
            company_name="CTCP FPT",
            summary=_summary(),
            research_context=context,
        )
    )

    artifact = tmp_path / "reports" / "debug" / "FPT_source_backed_evidence.json"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "REDACTME123" not in text
    assert "REDACTME456" not in text
    assert "<redacted>" in text
