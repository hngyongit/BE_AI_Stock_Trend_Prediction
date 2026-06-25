import json

from analyse.config.settings import Settings
from analyse.schemas.report import ProviderMetadata, ReportData, ReportGenerateResponse
from analyse.schemas.research import ExternalResearchContext
from analyse.services.html_service import HtmlService
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.services.report_missing_field_auditor import ReportMissingFieldAuditor
from analyse.services.report_service import ReportService
from analyse.services.summary_service import SummaryService


def _settings(**overrides):
    base = {
        "ENABLE_SCORING": True,
        "EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON": False,
        "VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON": False,
    }
    base.update(overrides)
    return Settings(**base)


def _base_payload():
    return {
        "symbol": "FPT",
        "exchange": "HOSE",
        "company": "CTCP FPT",
        "_source_success": {"watchlist_loaded": True, "analysis_data_loaded": True, "backend_stock_detail_loaded": True},
        "latestMarket": {"close_price": 110, "volume": 1000, "eps": 1000, "pe": 10, "pb": 2, "roe": 18},
        "priceHistory": [
            {"time": "2026-04-01", "close": 100, "volume": 1000},
            {"time": "2026-06-01", "close": 110, "volume": 1200},
        ],
        "financials": {
            "periods": [
                {"period": "Q1/2026", "revenue": 1200, "gross_profit": 400, "operating_profit": 260, "profit_before_tax": 240, "profit_after_tax": 200, "total_assets": 5000, "total_liabilities": 2100, "equity": 2900, "eps": 1000, "roe": 18, "roa": 7},
                {"period": "Q4/2025", "revenue": 1100, "gross_profit": 360, "operating_profit": 230, "profit_before_tax": 210, "profit_after_tax": 180, "total_assets": 4800, "total_liabilities": 2000, "equity": 2800, "eps": 900, "roe": 17, "roa": 6.8},
                {"period": "Q3/2025", "revenue": 1000, "gross_profit": 330, "operating_profit": 200, "profit_before_tax": 190, "profit_after_tax": 160, "total_assets": 4600, "total_liabilities": 1900, "equity": 2700, "eps": 850, "roe": 16, "roa": 6.5},
            ],
            "source": "Vietstock Finance BCTC",
        },
        "hoseMarketContext": {
            "indexName": "VN-Index",
            "indexValue": 1300,
            "changePercent": 0.5,
            "matchedVolume": 500000000,
            "tradingValueBillion": 30989.0,
            "marketScore": 65,
            "status": "Khá tích cực",
        },
        "industryPeerContext": {
            "peers": [
                {"symbol": f"P{i}", "company": f"Peer {i}", "source": "Vietstock Finance", "pe": 10 + i, "pb": 1.5, "roe": 12, "close_price": 20 + i}
                for i in range(1, 10)
            ]
        },
        "dataQuality": {
            "financialsLoaded": True,
            "financialPeriodsCount": 3,
            "priceHistoryPoints": 2,
            "marketContextLoaded": True,
            "peerContextLoaded": True,
            "warnings": [],
            "missingFields": [],
        },
    }


def _summary(payload=None):
    return SummaryService(settings=_settings()).build_summary(
        symbol="FPT",
        stock_detail=payload or _base_payload(),
        research_context=ExternalResearchContext(
            enabled=True,
            status="success",
            items=[{"source": "Google News", "type": "news", "title": f"Tin {idx}"} for idx in range(10)],
        ),
        scope_exchange="HOSE",
        warnings=[],
    )


def _card(section, label):
    return next(card for card in section["cards"] if card["label"] == label)


def test_chart_period_change_is_calculated_from_price_history():
    summary = _summary()
    quick = summary["report_presentation"]["quick_overview"]

    assert quick["chart_period_change_pct"] == 10.0
    assert _card(quick, "Biến động kỳ chart")["value"] == "+10,00%"


def test_chart_period_change_maps_to_quick_overview_card():
    summary = _summary()
    card = _card(summary["report_presentation"]["quick_overview"], "Biến động kỳ chart")

    assert card["status"] == "available"
    assert card["raw_value"] == 10.0
    assert card["source"] == "Dữ liệu giá và thanh khoản"


def test_quick_overview_does_not_show_unverified_when_price_history_exists():
    summary = _summary()
    card = _card(summary["report_presentation"]["quick_overview"], "Biến động kỳ chart")

    assert card["value"] != "Chưa xác minh"


def test_invalid_first_price_does_not_crash_chart_period_change():
    payload = _base_payload()
    payload["priceHistory"] = [{"time": "2026-04-01", "close": 0}, {"time": "2026-06-01", "close": 110}]
    summary = _summary(payload)

    card = _card(summary["report_presentation"]["quick_overview"], "Biến động kỳ chart")
    assert card["status"] == "missing"
    assert "không hợp lệ" in card["value"]


def test_explicit_backend_period_change_wins_over_calculation():
    payload = _base_payload()
    payload["chartPeriodChangePct"] = 4.25
    summary = _summary(payload)

    quick = summary["report_presentation"]["quick_overview"]
    assert quick["chart_period_change_pct"] == 4.25
    assert quick["summary_bar"]["chart_return"] == 4.25


def test_raw_market_trading_value_billion_maps_to_card():
    summary = _summary()
    card = _card(summary["report_presentation"]["market_context_view"], "Giá trị giao dịch")

    assert card["raw_value"] == 30989.0
    assert card["status"] == "available"
    assert card["value"] == "30.989,0 tỷ đồng"


def test_raw_market_snake_case_trading_value_maps_to_card():
    payload = _base_payload()
    payload["hoseMarketContext"].pop("tradingValueBillion")
    payload["hoseMarketContext"]["trading_value_billion"] = 12345.6
    summary = _summary(payload)

    card = _card(summary["report_presentation"]["market_context_view"], "Giá trị giao dịch")
    assert card["raw_value"] == 12345.6
    assert card["value"] != "Chưa xác minh"


def test_raw_market_total_trading_value_alias_maps_to_card():
    payload = _base_payload()
    payload["hoseMarketContext"].pop("tradingValueBillion")
    payload["hoseMarketContext"]["totalTradingValue"] = 30_989_000_000_000
    summary = _summary(payload)

    card = _card(summary["report_presentation"]["market_context_view"], "Giá trị giao dịch")
    assert card["raw_value"] == 30989.0
    assert card["value"] == "30.989,0 tỷ đồng"


def test_market_paragraph_and_market_card_are_consistent():
    view = _summary()["report_presentation"]["market_context_view"]

    assert "giá trị giao dịch" in view["narrative"]
    assert _card(view, "Giá trị giao dịch")["value"] in view["narrative"]


def test_missing_trading_value_only_affects_trading_value_card():
    payload = _base_payload()
    payload["hoseMarketContext"].pop("tradingValueBillion")
    summary = _summary(payload)
    cards = {card["label"]: card for card in summary["report_presentation"]["market_context_view"]["cards"]}

    assert cards["Giá trị giao dịch"]["status"] == "missing"
    assert cards["Biến động"]["status"] == "available"


def test_three_financial_periods_build_financial_table():
    summary = _summary()
    table = summary["report_presentation"]["financial_table"]

    assert table["status"] == "available"
    assert table["period_count"] == 3
    assert table["columns"] == ["Chỉ tiêu", "Q1/2026", "Q4/2025", "Q3/2025"]
    assert any(row["metric"] == "Doanh thu" for row in table["rows"])


def test_price_history_close_alias_calculates_chart_period_change():
    payload = _base_payload()
    payload["priceHistory"] = [
        {"date": "2026-04-01", "c": "100"},
        {"date": "2026-06-01", "matchedPrice": "104.25"},
    ]
    summary = _summary(payload)

    card = _card(summary["report_presentation"]["quick_overview"], "Biến động kỳ chart")
    assert card["raw_value"] == 4.25
    assert card["value"] == "+4,25%"


def test_financial_period_count_and_table_source_are_consistent():
    summary = _summary()
    quick_count = _card(summary["report_presentation"]["quick_overview"], "Số kỳ BCTC")["raw_value"]
    table = summary["report_presentation"]["financial_table"]

    assert quick_count == table["period_count"] == 3
    assert table["source"] == "Vietstock Finance BCTC"


def test_bank_financials_build_bank_specific_rows():
    payload = _base_payload()
    payload["financials"]["periods"] = [
        {"period": "Q1/2026", "net_interest_income": 100, "net_fee_income": 20, "profit_before_tax": 60, "profit_after_tax": 45, "total_assets": 10000, "customer_loans": 7000, "customer_deposits": 8000, "equity": 900, "eps": 1000, "roe": 18, "roa": 1.5},
        {"period": "Q4/2025", "net_interest_income": 90, "net_fee_income": 18, "profit_before_tax": 55, "profit_after_tax": 40, "total_assets": 9500, "customer_loans": 6800, "customer_deposits": 7700, "equity": 850, "eps": 950, "roe": 17, "roa": 1.4},
        {"period": "Q3/2025", "net_interest_income": 85, "net_fee_income": 16, "profit_before_tax": 50, "profit_after_tax": 38, "total_assets": 9200, "customer_loans": 6500, "customer_deposits": 7400, "equity": 830, "eps": 900, "roe": 16, "roa": 1.3},
    ]
    summary = _summary(payload)
    metrics = [row["metric"] for row in summary["report_presentation"]["financial_table"]["rows"]]

    assert "Thu nhập lãi thuần" in metrics
    assert "Cho vay khách hàng" in metrics


def test_non_bank_financials_build_normal_rows():
    metrics = [row["metric"] for row in _summary()["report_presentation"]["financial_table"]["rows"]]

    assert "Doanh thu" in metrics
    assert "Lợi nhuận sau thuế" in metrics


def test_missing_individual_metric_does_not_hide_whole_financial_table():
    payload = _base_payload()
    payload["financials"]["periods"][1].pop("gross_profit")
    summary = _summary(payload)
    row = next(row for row in summary["report_presentation"]["financial_table"]["rows"] if row["metric"] == "Lợi nhuận gộp")

    assert summary["report_presentation"]["financial_table"]["status"] == "available"
    assert row["values"][1] == "Chưa xác minh"


def test_action_plan_arrays_build_action_table():
    service = SummaryService(settings=_settings())
    summary = _summary()
    summary["action_plan"] = {"shortTerm": ["Theo dõi thanh khoản"], "riskManagement": ["Quản trị rủi ro nếu giá gãy hỗ trợ"]}
    refreshed = service.refresh_report_presentation(summary)

    rows = refreshed["report_presentation"]["action_table"]["rows"]
    assert rows
    assert rows[0]["timeframe"] == "Ngắn hạn"


def test_action_table_fills_safe_educational_columns():
    service = SummaryService(settings=_settings(DEFAULT_MAX_POSITION_PCT=12, DEFAULT_RISK_PER_TRADE_PCT=1))
    summary = _summary()
    summary["action_plan"] = {"shortTerm": [{"action": "Theo dõi thanh khoản", "price_zone": "Chưa xác minh"}]}
    refreshed = service.refresh_report_presentation(summary)

    row = refreshed["report_presentation"]["action_table"]["rows"][0]
    for key in ("action", "condition", "price_zone", "position_size", "stop_loss", "note"):
        assert row[key]
        assert row[key] != "Chưa xác minh"
    assert "12%" in row["position_size"]
    assert "1%" in row["stop_loss"]


def test_scenario_matrix_builds_scenario_table():
    service = SummaryService(settings=_settings())
    summary = _summary()
    summary["scenarioMatrix"] = [{"scenario": "Tích cực", "condition": "Thanh khoản cải thiện", "response": "Theo dõi xác nhận"}]
    refreshed = service.refresh_report_presentation(summary)

    assert refreshed["report_presentation"]["scenario_table"]["rows"][0]["scenario"] == "Tích cực"


def test_watchpoints_and_risk_management_build_checklist():
    service = SummaryService(settings=_settings())
    summary = _summary()
    summary["watchPoints"] = ["Kiểm tra thanh khoản"]
    summary["riskManagement"] = ["Theo dõi rủi ro thị trường"]
    refreshed = service.refresh_report_presentation(summary)

    labels = [item["label"] for item in refreshed["report_presentation"]["checklist"]["items"]]
    assert "Kiểm tra xu hướng giá" in labels or "Kiểm tra rủi ro chính" in labels


def test_fallback_monitoring_rows_created_from_existing_score_or_risk_data():
    summary = _summary()

    assert summary["report_presentation"]["action_table"]["rows"]
    assert summary["report_presentation"]["scenario_table"]["rows"]
    assert summary["report_presentation"]["checklist"]["items"]


def test_action_table_has_no_personalized_buy_sell_language():
    service = SummaryService(settings=_settings())
    summary = _summary()
    summary["action_plan"] = {"short_term": ["mua ngay khi tăng giá", "bán ngay nếu giảm"]}
    refreshed = service.refresh_report_presentation(summary)
    serialized = json.dumps(refreshed["report_presentation"]["action_table"], ensure_ascii=False).lower()

    assert "mua ngay" not in serialized
    assert "bán ngay" not in serialized


def test_available_coverage_never_pairs_with_unverified_value():
    items = _summary()["report_presentation"]["data_coverage"]["items"]

    assert not any(item["status"] == "available" and item["value"] == "Chưa xác minh" for item in items)


def test_source_backed_enrichment_policy_is_present():
    policy = _summary()["report_presentation"]["source_backed_enrichment"]

    assert policy["enabled"] is True
    assert policy["numeric_facts_require_source"] is True
    assert "backend" in policy["allowed_sources"]


def test_financial_coverage_with_three_periods_shows_three_periods():
    item = next(item for item in _summary()["report_presentation"]["data_coverage"]["items"] if item["key"] == "financials")

    assert item["value"] == "3 kỳ"


def test_peer_coverage_shows_peer_count():
    item = next(item for item in _summary()["report_presentation"]["data_coverage"]["items"] if item["key"] == "peers")

    assert item["value"] == "9 peer"


def test_news_coverage_shows_news_count():
    item = next(item for item in _summary()["report_presentation"]["data_coverage"]["items"] if item["key"] == "external_news")

    assert item["value"] == "10 tin"


def test_watchlist_coverage_shows_verified_permission_label():
    item = next(item for item in _summary()["report_presentation"]["data_coverage"]["items"] if item["key"] == "watchlist")

    assert item["value"] == "Đã xác minh quyền phân tích"


def test_cafef_company_source_is_specific_and_success_when_company_data_exists():
    sources = sanitize_data_source_statuses([{"name": "CafeF", "type": "external_company", "status": "success", "detail": "fields=3; leadership_rows=1; ownership_rows=1"}])

    assert sources[0]["name"] == "CafeF thông tin doanh nghiệp"
    assert sources[0]["status_label"] == "Đã ghi nhận"


def test_cafef_financial_source_is_specific_and_success_when_periods_exist():
    sources = sanitize_data_source_statuses([{"name": "CafeF", "type": "external_financial", "status": "success", "detail": "periods=3"}])

    assert sources[0]["name"] == "CafeF tài chính"
    assert sources[0]["status"] == "success"
    assert sources[0]["status_label"] == "Đã ghi nhận"


def test_cafef_financial_partial_only_when_marked_partial_with_periods():
    sources = sanitize_data_source_statuses([{"name": "CafeF tài chính", "type": "external_financial", "status": "partial", "detail": "periods=2"}])

    assert sources[0]["status"] == "partial"
    assert sources[0]["status_label"] == "Ghi nhận một phần"


def test_cafef_financial_insufficient_when_zero_periods():
    sources = sanitize_data_source_statuses([{"name": "CafeF tài chính", "type": "external_financial", "status": "partial", "detail": "periods=0"}])

    assert sources[0]["status"] == "insufficient"


def test_no_duplicate_generic_cafef_source_names():
    sources = sanitize_data_source_statuses(
        [
            {"name": "CafeF", "type": "external_company", "status": "success", "detail": "fields=2"},
            {"name": "CafeF", "type": "external_financial", "status": "success", "detail": "periods=3"},
        ]
    )

    assert {source["name"] for source in sources} == {"CafeF thông tin doanh nghiệp", "CafeF tài chính"}


def test_generic_vietstock_source_names_are_specific():
    sources = sanitize_data_source_statuses(
        [
            {"name": "Vietstock", "type": "external_financial", "status": "success", "detail": "periods=3"},
            {"name": "Vietstock", "type": "external_peer", "status": "success", "detail": "normalized_peers=9"},
        ]
    )

    assert {source["name"] for source in sources} == {"Vietstock Finance BCTC", "Vietstock peer cùng ngành"}


def test_source_rows_do_not_show_raw_debug_details():
    sources = sanitize_data_source_statuses([{"name": "CafeF tài chính", "type": "external_financial", "status": "failed", "detail": "https://cafef.vn/x; page.goto timeout; periods=0"}])
    serialized = json.dumps(sources, ensure_ascii=False)

    assert "https://cafef.vn" not in serialized
    assert "page.goto" not in serialized
    assert "periods=0" not in serialized


def test_api_response_contract_remains_code_message_data():
    response = ReportGenerateResponse(
        data=ReportData(
            report_id="FPT_HOSE_20260623_100000",
            generated_at="2026-06-23T10:00:00+07:00",
            symbol="FPT",
            provider=ProviderMetadata(name="openai", model="gpt-test", status="success"),
            summary={"report_presentation": _summary()["report_presentation"]},
        )
    ).model_dump()

    assert set(response.keys()) == {"code", "message", "data"}


def test_report_status_not_failed_when_only_history_or_source_is_partial():
    service = ReportService(settings=_settings(ENABLE_AI_REPORT_HISTORY=True))
    status = service._derive_report_status(
        analysis_status="success",
        history_status="failed",
        source_status="partial",
        warnings=["optional source failed"],
        has_report_content=True,
    )

    assert status == "success_with_warnings"


def test_report_data_exposes_separate_status_fields():
    response = ReportGenerateResponse(
        data=ReportData(
            report_id="FPT_HOSE_20260623_100000",
            generated_at="2026-06-23T10:00:00+07:00",
            symbol="FPT",
            analysis_status="success",
            history_status="failed",
            source_status="partial",
            report_status="success_with_warnings",
            provider=ProviderMetadata(name="openai", model="gpt-test", status="failed"),
            summary={"report_presentation": _summary()["report_presentation"]},
        )
    ).model_dump()

    assert response["data"]["report_status"] == "success_with_warnings"
    assert response["data"]["analysis_status"] == "success"
    assert response["data"]["history_status"] == "failed"
    assert response["data"]["source_status"] == "partial"


def test_existing_html_report_template_still_renders_with_new_presentation(tmp_path):
    summary = _summary()
    html = HtmlService(Settings(REPORT_OUTPUT_DIR=str(tmp_path), REPORT_CHART_ENGINE="inline_svg")).build("report", summary)

    assert '<section id="market-context">' in html
    assert '<section id="financial-statement-analysis">' in html
    assert '<section id="action-plan">' in html
    assert '<section id="scenario-matrix">' in html


def test_debug_scrubber_removes_secret_like_values(tmp_path):
    service = SummaryService(settings=_settings(EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True, REPORT_OUTPUT_DIR=str(tmp_path / "reports")))
    payload = service._scrub_debug_payload({"token": "Bearer abc.def", "OPENAI_API_KEY": "sk-secret123456789", "nested": {"password": "pw"}})

    assert "abc.def" not in json.dumps(payload)
    assert "sk-secret" not in json.dumps(payload)
    assert payload["nested"]["password"] == "<redacted>"


def test_missing_field_auditor_writes_scrubbed_debug_artifact(tmp_path):
    settings = _settings(REPORT_OUTPUT_DIR=str(tmp_path / "reports"), MISSING_FIELD_ENRICHMENT_WRITE_DEBUG=True)
    auditor = ReportMissingFieldAuditor(settings)
    response = {
        "data": {
            "symbol": "FPT",
            "summary": {
                "price_history": [{"close": 100}, {"close": 110}],
                "momentum": {"chart_period_change_pct": 10},
                "report_presentation": {
                    "quick_overview": {"cards": [{"label": "Biến động kỳ chart", "value": "Chưa xác minh", "status": "missing"}]},
                    "source_backed_enrichment": {"authorization": "Bearer abc.def"},
                },
            },
            "data_sources": [{"name": "CafeF", "type": "external_financial", "status": "partial"}],
        }
    }

    records = auditor.save_debug("FPT", response)
    payload = json.loads((tmp_path / "reports" / "debug" / "FPT_missing_field_audit.json").read_text(encoding="utf-8"))

    assert records
    assert payload["records"][0]["section"] == "quick_overview"
    assert "abc.def" not in json.dumps(payload)
