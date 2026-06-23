from analyse.config.settings import Settings
from analyse.schemas.research import ExternalResearchContext
from analyse.services.scoring_service import ScoringService
from analyse.services.stock_data_service import StockDataService
from analyse.services.stock_data_service import normalize_vietnamese_person_name
from analyse.services.stock_data_service import normalize_vietnamese_person_name_ascii
from analyse.services.summary_service import SummaryService


def sample_analysis_data():
    return {
        "symbol": "FPT",
        "exchange": "HOSE",
        "company": "CTCP FPT",
        "latestMarket": {
            "close_price": 71500,
            "volume": 14295100,
            "market_cap": 121801,
            "eps": 6010,
            "pe": 10.73,
            "forward_pe": 10.49,
            "pb": 3.04,
            "beta": 0.88,
            "roe": 18.93,
            "ros": 19.85,
            "roaa": 3.17,
            "foreign_net": 1843600,
        },
        "priceHistory": [
            {"time_id": 20260601, "close_price": 68000, "close": 68000, "volume": 10000000},
            {"time_id": 20260610, "close_price": 70000, "close": 70000, "volume": 11000000},
            {"time_id": 20260619, "close_price": 71500, "close": 71500, "volume": 14295100},
        ],
        "financials": {
            "periods": [
                {"period": "Q2/2026", "revenue": 123456, "gross_profit": 45000, "operating_profit": 32000, "profit_before_tax": 25000, "profit_after_tax": 21000, "parent_profit": 20000, "eps": 1234, "total_assets": 500000, "total_liabilities": 200000, "equity": 300000},
                {"period": "Q1/2026", "revenue": 110000, "gross_profit": 40000, "operating_profit": 30000, "profit_before_tax": 23000, "profit_after_tax": 19000, "parent_profit": 18000, "eps": 1100, "total_assets": 480000, "total_liabilities": 195000, "equity": 285000},
                {"period": "Q4/2025", "revenue": 100000, "gross_profit": 37000, "operating_profit": 28000, "profit_before_tax": 22000, "profit_after_tax": 18000, "parent_profit": 17000, "eps": 1000, "total_assets": 470000, "total_liabilities": 190000, "equity": 280000},
                {"period": "Q3/2025", "revenue": 95000, "profit_after_tax": 17000, "parent_profit": 16000},
            ]
        },
        "financialBalance": {"period": "Q2/2026", "total_assets": 500000, "total_liabilities": 200000, "equity": 300000},
        "hoseMarketContext": {"vnindex": 1300.12, "change_percent": -0.8, "foreign_net": -123456, "regime": "risk_off"},
        "marketGeneralContext": {"exchange": "HOSE", "source": "mongo:test"},
        "industryPeerContext": {
            "industry": {"sector": "Công nghệ thông tin", "industry": "Dịch vụ CNTT"},
            "peers": [{"symbol": "CMG", "company": "CMC", "exchange": "HOSE", "close_price": 123, "pe": 12.3, "pb": 2.1, "roe": 15.2, "market_cap": 123456, "profit_after_tax": 123456, "revenue": 123456, "momentum_1m": 5.2}],
        },
        "sameIndustryRecommendation": {"candidates": [{"symbol": "CMG", "company": "CMC", "roe": 15.2}], "method": "mock"},
        "dataQuality": {
            "financialsLoaded": True,
            "financialPeriodsCount": 4,
            "priceHistoryPoints": 3,
            "marketContextLoaded": True,
            "peerContextLoaded": True,
            "missingFields": [],
            "warnings": [],
        },
    }


def test_summary_maps_analysis_data_contract_fields():
    service = SummaryService(settings=Settings(ENABLE_SCORING=True))
    summary = service.build_summary(
        symbol="FPT",
        stock_detail=sample_analysis_data(),
        research_context=ExternalResearchContext(enabled=False, status="disabled", items=[]),
        scope_exchange="HOSE",
        warnings=[],
    )

    assert summary["data_coverage"]["financials_loaded"] is True
    assert summary["bctc_3q"]["has_bctc"] is True
    assert len(summary["bctc_3q"]["periods"]) == 3
    assert summary["bctc_3q"]["total_periods_available"] == 4
    assert summary["financial_balance"]["equity"] == 300000
    assert summary["hose_market_context"]["vnindex"] == 1300.12
    assert summary["industry_peer_context"]["peers"][0]["symbol"] == "CMG"
    assert summary["market_general_context"]["exchange"] == "HOSE"
    assert summary["same_industry_recommendation"]["candidates"][0]["symbol"] == "CMG"
    assert isinstance(summary["scores"]["overall_score"], int)


def test_scoring_service_returns_numeric_scores_and_labels():
    scores = ScoringService().build_scores({
        "latest_market": sample_analysis_data()["latestMarket"],
        "price_history": sample_analysis_data()["priceHistory"],
        "financials": sample_analysis_data()["financials"],
        "hose_market_context": sample_analysis_data()["hoseMarketContext"],
    })

    for key in (
        "valuation_score",
        "quality_score",
        "growth_score",
        "momentum_score",
        "liquidity_score",
        "size_score",
        "risk_score",
        "overall_score",
    ):
        assert isinstance(scores[key], int)
        assert 0 <= scores[key] <= 100
    assert scores["risk_label"] in ScoringService.VALID_RISK_LABELS
    assert scores["overall_label"] in ScoringService.VALID_OVERALL_LABELS
    assert scores["score_explanations"]


def test_scoring_missing_data_returns_partial_scores_without_crash():
    scores = ScoringService().build_scores({"latest_market": {}, "price_history": [], "financials": {"periods": []}})

    assert isinstance(scores["overall_score"], int)
    assert scores["risk_label"] in ScoringService.VALID_RISK_LABELS
    assert scores["score_confidence"] < 0.6
    assert scores["score_explanations"]


def test_scoring_confidence_is_capped_when_peer_or_units_missing():
    data = sample_analysis_data()
    scores_no_peer = ScoringService().build_scores(
        {
            "latest_market": data["latestMarket"],
            "price_history": data["priceHistory"],
            "financials": data["financials"],
            "hose_market_context": data["hoseMarketContext"],
            "industry_peer_context": {"peers": []},
        }
    )
    assert scores_no_peer["score_confidence"] <= 0.75

    scores_unclear_units = ScoringService().build_scores(
        {
            "latest_market": data["latestMarket"],
            "price_history": data["priceHistory"],
            "financials": data["financials"],
            "hose_market_context": data["hoseMarketContext"],
            "industry_peer_context": data["industryPeerContext"],
            "data_quality": {"warnings": ["Đơn vị tiền tệ/market_cap cần kiểm tra thêm vì model hiện chưa lưu metadata đơn vị."]},
        }
    )
    assert scores_unclear_units["score_confidence"] <= 0.80


def test_summary_business_overview_uses_industry_without_duplicate_wording():
    service = SummaryService(settings=Settings(ENABLE_SCORING=True))
    data = sample_analysis_data()
    data["industryPeerContext"] = {
        "industry": {
            "sector": "Tài chính",
            "industry_group": "Tổ chức tín dụng",
            "industry": "Ngân hàng",
            "source": "Vietstock Finance",
        },
        "peers": [],
    }

    summary = service.build_summary(
        symbol="VCB",
        stock_detail=data,
        research_context=ExternalResearchContext(enabled=False, status="disabled", items=[]),
        scope_exchange="HOSE",
        warnings=[],
    )

    description = summary["report_presentation"]["business_overview"]["description"]
    assert "nhóm ngành Tổ chức tín dụng" in description
    assert "ngành chi tiết Ngân hàng" in description
    assert "ngành cấp cao" not in description
    assert "nhóm nhóm ngành" not in description


def test_company_overview_merges_cafef_name_and_vietstock_industry_without_unknown_rows():
    stock_service = StockDataService()
    data = {
        "symbol": "VCB",
        "exchange": "HOSE",
        "company": "Ngân hàng TMCP Ngoại thương Việt Nam",
        "industryPeerContext": {
            "industry": {
                "sector": "Tài chính",
                "industry_group": "Tổ chức tín dụng",
                "industry": "Ngân hàng",
                "source": "Vietstock Finance",
            },
            "peers": [],
        },
    }
    merged = stock_service.merge_company_fallback(
        data,
        {
            "status": "success",
            "symbol": "VCB",
            "company_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
            "exchange": "HOSE",
            "source": "CafeF",
            "source_url": "https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn",
        },
    )
    summary = SummaryService(settings=Settings(ENABLE_SCORING=True)).build_summary(
        symbol="VCB",
        stock_detail=merged,
        research_context=ExternalResearchContext(enabled=False, status="disabled", items=[]),
        scope_exchange="HOSE",
        warnings=[],
    )

    overview = summary["report_presentation"]["business_overview"]
    description = overview["description"]
    industry = overview["industry"]

    assert overview["company_name"] == "Ngân hàng TMCP Ngoại thương Việt Nam"
    assert industry["sector"] == "Tài chính"
    assert industry["industry_group"] == "Tổ chức tín dụng"
    assert industry["industry"] == "Ngân hàng"
    assert "CafeF thông tin doanh nghiệp" in overview["source_note"]
    assert "Vietstock Finance" in overview["source_note"]
    assert "nhóm nhóm ngành" not in description
    assert "Chưa xác minh" not in description


def test_normalize_vietnamese_person_name_removes_honorifics():
    assert normalize_vietnamese_person_name("Ông Trần Đình Long") == "trần đình long"
    assert normalize_vietnamese_person_name("Bà Vũ Thị Hiền") == "vũ thị hiền"
    assert normalize_vietnamese_person_name_ascii("Trần Đình Long") == "tran dinh long"


def test_leadership_is_enriched_from_matching_shareholder_rows():
    stock_service = StockDataService()
    overview, debug = stock_service.enrich_leadership_with_ownership(
        {
            "leadership": [
                {"name": "Ông Trần Đình Long", "position": "Chủ tịch HĐQT", "source": "CafeF"},
                {"name": "Bà Vũ Thị Hiền", "position": "Phó chủ tịch HĐQT", "source": "CafeF"},
            ],
            "ownership": [
                {"holder": "Trần Đình Long", "shares": 2178000179, "ownership_percent": 25.0, "source": "CafeF"},
                {"holder": "Vũ Thị Hiền", "shares": 478000000, "ownership_percent": 5.5, "source": "CafeF"},
            ],
        }
    )

    leadership = overview["leadership"]
    assert leadership[0]["position"] == "Chủ tịch HĐQT"
    assert leadership[0]["shares"] == 2178000179
    assert leadership[0]["ownership_percent"] == 25.0
    assert leadership[0]["ownership_match"] == "matched_by_normalized_name"
    assert leadership[0]["ownership_match_confidence"] == 0.95
    assert leadership[0]["ownership_note"] == "Đối chiếu từ bảng cổ đông lớn CafeF"
    assert leadership[1]["shares"] == 478000000
    assert len(debug["matches"]) == 2


def test_leadership_ownership_merge_does_not_match_organizations_or_fabricate_values():
    overview, debug = StockDataService.enrich_leadership_with_ownership(
        {
            "leadership": [{"name": "Ông Nguyễn Văn A", "position": "Tổng giám đốc"}],
            "ownership": [
                {"holder": "Dragon Capital", "shares": 1000, "ownership_percent": 1.0},
                {"holder": "Norges Bank", "shares": 2000, "ownership_percent": 2.0},
            ],
        }
    )

    leader = overview["leadership"][0]
    assert leader["shares"] is None
    assert leader["ownership_percent"] is None
    assert leader["ownership_match"] == "not_found"
    assert debug["matches"] == []


def test_market_context_maps_aliases_to_user_ready_cards():
    service = SummaryService(settings=Settings(ENABLE_SCORING=True))
    data = sample_analysis_data()
    data["hoseMarketContext"] = {
        "indexName": "VN-Index",
        "indexValue": 1857.91,
        "changePercent": 0.6,
        "matchedVolume": 517600000,
        "tradingValueBillion": 14597.1,
        "marketScore": 65,
        "status": "Khá tích cực",
    }

    summary = service.build_summary(
        symbol="FPT",
        stock_detail=data,
        research_context=ExternalResearchContext(enabled=False, status="disabled", items=[]),
        scope_exchange="HOSE",
        warnings=[],
    )

    normalized = summary["hose_market_context"]
    view = summary["report_presentation"]["market_context_view"]
    cards = {card["label"]: card["value"] for card in view["cards"]}

    assert normalized["index_value"] == 1857.91
    assert normalized["change_percent"] == 0.6
    assert normalized["market_health_score"] == 65
    assert cards["Chỉ số"] == "VN-Index 1,857.91"
    assert cards["Biến động"] == "0.6%"
    assert cards["Thanh khoản"] == "517.6 triệu cp"
    assert cards["Giá trị giao dịch"] == "14,597.1 tỷ đồng"
    assert cards["Trạng thái"] == "Khá tích cực"
    assert cards["Điểm sức khỏe thị trường"] == "65/100"


def test_market_context_missing_fields_are_per_card_not_whole_section():
    service = SummaryService(settings=Settings(ENABLE_SCORING=True))
    data = sample_analysis_data()
    data["hoseMarketContext"] = {"changePercent": -0.2, "healthScore": 55}

    summary = service.build_summary(
        symbol="FPT",
        stock_detail=data,
        research_context=ExternalResearchContext(enabled=False, status="disabled", items=[]),
        scope_exchange="HOSE",
        warnings=[],
    )

    cards = {card["label"]: card["value"] for card in summary["report_presentation"]["market_context_view"]["cards"]}
    assert cards["Chỉ số"] == "Chưa xác minh"
    assert cards["Biến động"] == "-0.2%"
    assert cards["Điểm sức khỏe thị trường"] == "55/100"


def test_summary_risks_do_not_repeat_source_process_notes():
    service = SummaryService(settings=Settings(ENABLE_SCORING=True))
    data = sample_analysis_data()
    data["dataQuality"]["warnings"] = [
        "Báo cáo đã đối chiếu thông tin doanh nghiệp từ CafeF.",
        "Báo cáo đã bổ sung dữ liệu tài chính từ Vietstock Finance để đối chiếu với dữ liệu nội bộ.",
        "Dữ liệu peer công khai chưa đủ để lập bảng so sánh định lượng.",
    ]

    summary = service.build_summary(
        symbol="FPT",
        stock_detail=data,
        research_context=ExternalResearchContext(enabled=False, status="disabled", items=[]),
        scope_exchange="HOSE",
        warnings=[],
    )

    risks = " ".join(summary["report_presentation"]["executive_summary"]["key_risks"])
    assert "CafeF" not in risks
    assert "Vietstock" not in risks
    assert "Dữ liệu ngành/peer hiện chưa đủ" in risks or "peer" in risks.lower()
