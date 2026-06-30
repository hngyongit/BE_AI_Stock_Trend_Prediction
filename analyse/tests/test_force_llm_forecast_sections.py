import json

from analyse.config.settings import Settings
from analyse.prompts.report_prompts import build_report_prompt
from analyse.prompts.system_prompts import get_system_prompt
from analyse.schemas.common import api_success
from analyse.services.report_forecast_normalizer import ReportForecastNormalizer
from analyse.services.report_service import ReportService
from analyse.services.summary_service import SummaryService


def _settings(**overrides):
    values = {
        "_env_file": None,
        "EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON": False,
        "VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON": False,
    }
    values.update(overrides)
    return Settings(**values)


def _summary():
    return {
        "symbol": "FPT",
        "company": "CTCP FPT",
        "scope_exchange": "HOSE",
        "latest_market": {"close_price": 110, "volume": 1_200_000},
        "momentum": {"chart_period_change_pct": 7.5, "chart_points": 60},
        "hose_market_context": {"market_health_score": 65, "status": "Khá tích cực"},
        "scores": {"overall_score": 71, "risk_score": 42, "score_confidence": 0.72, "risk_label": "Trung bình"},
        "data_coverage": {
            "financial_periods_count": 3,
            "price_history_points": 60,
            "latest_price_loaded": True,
            "market_context_loaded": True,
            "watchlist_loaded": True,
            "external_research_items": 2,
        },
        "bctc_3q": {
            "source": "Vietstock Finance BCTC",
            "periods": [
                {"period": "Q1/2026", "revenue": 1200, "profit_after_tax": 200, "equity": 2900},
                {"period": "Q4/2025", "revenue": 1100, "profit_after_tax": 180, "equity": 2800},
                {"period": "Q3/2025", "revenue": 1000, "profit_after_tax": 160, "equity": 2700},
            ],
        },
        "industry_peer_context": {"peers": [{"symbol": "CMG"}, {"symbol": "ELC"}]},
        "external_research_context": {"items": [{"title": "FPT kết quả kinh doanh tích cực"}, {"title": "Tin ngành công nghệ"}]},
        "investment_plan": {
            "time_horizon": "medium_term",
            "position_sizing": {"max_position_pct": 12, "risk_per_trade_pct": 1},
        },
        "weaknesses": ["Rủi ro thị trường chung nếu VN-Index chuyển sang trạng thái phòng thủ."],
    }


def test_llm_prompt_contains_mandatory_scenario_checklist_action_instructions():
    prompt = build_report_prompt({"symbol": "FPT", "summary": _summary()}, schema={})

    assert "MANDATORY OUTPUT REQUIREMENTS" in prompt
    assert "Return exactly 3 scenarios" in prompt
    assert "Return at least 5 checklist items" in prompt
    assert "at least 2 short_term actions" in prompt
    assert "at least 3 risk_management items" in prompt


def test_llm_prompt_bans_generic_missing_phrases_in_qualitative_sections():
    prompt = get_system_prompt()

    for phrase in ("Chưa xác minh", "Chưa xác định", "Không có dữ liệu", "N/A", "unknown", "null"):
        assert phrase in prompt
    assert "Không được dùng" in prompt
    assert "scenarios, checklist, action_plan" in prompt


def test_empty_llm_scenarios_are_replaced_by_three_fallback_scenarios():
    summary = _summary()
    summary["scenarios"] = []
    normalized, debug = ReportForecastNormalizer(_settings()).normalize_summary(summary)

    scenarios = normalized["forecast_scenarios"]
    assert [row["scenario"] for row in scenarios] == ["Tích cực", "Cơ sở", "Thận trọng"]
    assert len(scenarios) == 3
    assert sum(row["probability_pct"] for row in scenarios) == 100
    assert debug["scenarios_after"] == 3


def test_empty_llm_checklist_is_replaced_by_at_least_five_items():
    summary = _summary()
    summary["checklist"] = []
    normalized, debug = ReportForecastNormalizer(_settings()).normalize_summary(summary)

    assert len(normalized["checklist"]) >= 5
    assert all(item["source_basis"] for item in normalized["checklist"])
    assert debug["checklist_after"] >= 5


def test_empty_action_plan_is_replaced_by_required_action_items():
    summary = _summary()
    summary["action_plan"] = {}
    normalized, debug = ReportForecastNormalizer(_settings()).normalize_summary(summary)
    plan = normalized["action_plan"]

    assert len(plan["short_term"]) >= 2
    assert len(plan["medium_term"]) >= 2
    assert len(plan["watch_points"]) >= 3
    assert len(plan["risk_management"]) >= 3
    assert debug["action_rows_after"] >= 10


def test_banned_phrases_in_scenario_are_replaced():
    summary = _summary()
    summary["scenarios"] = [
        {
            "scenario": "Chưa xác định",
            "condition": "Chưa xác minh",
            "expected_behavior": "Không có dữ liệu",
            "risk_note": "unknown",
        }
    ]
    normalized, debug = ReportForecastNormalizer(_settings()).normalize_summary(summary)
    serialized = json.dumps(normalized["forecast_scenarios"], ensure_ascii=False)

    assert "Chưa xác minh" not in serialized
    assert "Chưa xác định" not in serialized
    assert "Không có dữ liệu" not in serialized
    assert "unknown" not in serialized
    assert debug["banned_phrases_found"]


def test_banned_phrases_in_checklist_are_replaced():
    summary = _summary()
    summary["checklist"] = [{"label": "Chưa xác minh", "note": "N/A", "source_basis": "unknown"}]
    normalized, _ = ReportForecastNormalizer(_settings()).normalize_summary(summary)
    serialized = json.dumps(normalized["checklist"], ensure_ascii=False)

    assert "Chưa xác minh" not in serialized
    assert "N/A" not in serialized
    assert "unknown" not in serialized
    assert len(normalized["checklist"]) >= 5


def test_missing_numeric_values_remain_null_not_fabricated():
    normalized, _ = ReportForecastNormalizer(_settings()).normalize_summary(_summary())

    assert normalized["action_plan"]["short_term"][0]["price_zone"] is None
    assert "price_zone_note" in normalized["action_plan"]["short_term"][0]
    assert "target_price" not in json.dumps(normalized["action_plan"], ensure_ascii=False)


def test_presentation_contains_mandatory_sections_after_normalization():
    settings = _settings()
    normalized, _ = ReportForecastNormalizer(settings).normalize_summary(_summary())
    refreshed = SummaryService(settings=settings).refresh_report_presentation(normalized)
    presentation = refreshed["report_presentation"]

    assert len(presentation["scenario_table"]["rows"]) >= 3
    assert len(presentation["checklist"]["items"]) >= 5
    assert len(presentation["action_table"]["rows"]) >= 2
    assert presentation["scenario_table"]["status"] == "available"
    assert presentation["checklist"]["status"] == "available"
    assert presentation["action_table"]["status"] == "available"


def test_api_response_envelope_remains_code_message_data():
    payload = api_success("ok", data={"summary": {}})

    assert {"code", "message", "data"}.issubset(payload)
    assert payload["success"] is True


def test_no_personalized_buy_sell_language_in_fallback_sections():
    normalized, _ = ReportForecastNormalizer(_settings()).normalize_summary(_summary())
    text = json.dumps(
        {
            "scenarios": normalized["forecast_scenarios"],
            "checklist": normalized["checklist"],
            "action_plan": normalized["action_plan"],
        },
        ensure_ascii=False,
    ).lower()

    assert "mua ngay" not in text
    assert "bán ngay" not in text
    assert "mua gấp" not in text
    assert "bán gấp" not in text


def test_mandatory_forecast_debug_artifact_is_scrubbed(tmp_path):
    settings = _settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
    )
    service = ReportService(settings=settings)
    summary = _summary()
    summary["scenarios"] = [{"scenario": "Chưa xác định", "condition": "Authorization: Bearer SHOULD_NOT_LEAK"}]

    service._enforce_mandatory_forecast_sections("FPT", summary, research_context=None)

    artifact = tmp_path / "reports" / "debug" / "FPT_mandatory_forecast_sections_validation.json"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "SHOULD_NOT_LEAK" not in text
    assert "Authorization: Bearer" not in text
