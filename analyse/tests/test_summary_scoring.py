from analyse.config.settings import Settings
from analyse.schemas.research import ExternalResearchContext
from analyse.services.scoring_service import ScoringService
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
