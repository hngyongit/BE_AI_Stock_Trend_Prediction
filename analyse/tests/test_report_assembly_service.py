from __future__ import annotations

from copy import deepcopy

from analyse.config.settings import Settings
from analyse.schemas.research import ExternalResearchContext, ResearchItem
from analyse.services.report_assembly_service import ReportAssemblyService


def _settings(tmp_path, **overrides):
    values = {
        "REPORT_OUTPUT_DIR": str(tmp_path / "reports"),
        "EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON": False,
        "VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON": False,
    }
    values.update(overrides)
    return Settings(**values)


def _summary() -> dict:
    return {
        "symbol": "FPT",
        "company": "CTCP FPT",
        "latest_market": {"close_price": 110, "volume": 1_200_000, "pe": 18, "pb": 3.2, "roe": 22},
        "momentum": {"chart_period_change_pct": 7.5, "chart_points": 60},
        "scores": {
            "overall_score": 71,
            "risk_score": 42,
            "score_confidence": 0.72,
            "overall_label": "Tích cực",
            "risk_label": "Trung bình",
        },
        "data_coverage": {
            "financial_periods_count": 3,
            "price_history_points": 60,
            "latest_price_loaded": True,
            "external_research_items": 1,
        },
        "bctc_3q": {
            "periods": [
                {
                    "period": "Q1/2026",
                    "revenue": 1200,
                    "gross_profit": 400,
                    "profit_after_tax": 200,
                    "total_assets": 5000,
                    "equity": 2900,
                    "eps": 1000,
                    "roe": 18,
                    "roa": 7,
                }
            ]
        },
        "action_plan": {"short_term": ["Theo dõi thanh khoản và vùng hỗ trợ gần nhất."]},
        "scenario_matrix": [{"scenario": "Tích cực", "condition": "Thanh khoản cải thiện."}],
        "checklist": [{"label": "Kiểm tra xu hướng giá", "status": "pending", "note": "Đối chiếu thanh khoản."}],
        "report_presentation": {"frontend_extra": {"layout": "compact"}},
        "custom_summary_key": {"kept": True},
    }


def _research_context() -> ExternalResearchContext:
    return ExternalResearchContext(
        enabled=True,
        status="success",
        items=[
            ResearchItem(
                source="CafeF",
                type="google_news_rss",
                title="FPT tăng trưởng",
                url="https://cafef.vn/fpt.html",
                snippet="FPT ghi nhận kết quả kinh doanh tích cực.",
                relevance_score=0.9,
            )
        ],
    )


def test_build_provider_metadata_returns_plain_current_shape(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))

    metadata = service.build_provider_metadata(
        provider="openai",
        model="gpt-4.1-mini",
        status="success",
        latency_ms=123,
    )

    assert metadata == {
        "name": "openai",
        "model": "gpt-4.1-mini",
        "status": "success",
        "latency_ms": 123,
    }
    assert isinstance(metadata, dict)


def test_build_provider_metadata_preserves_missing_provider_and_model_behavior(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))

    metadata = service.build_provider_metadata(provider=None, model=None)

    assert metadata == {
        "name": None,
        "model": None,
        "status": "not_implemented",
        "latency_ms": 0,
    }


def test_refresh_summary_presentation_preserves_unknown_summary_keys(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))
    summary = _summary()
    original = deepcopy(summary)

    refreshed = service.refresh_summary_presentation(
        summary=summary,
        research_context=_research_context(),
        warnings=["ignored by current refresh boundary"],
    )

    assert summary == original
    assert refreshed["custom_summary_key"] == {"kept": True}
    assert refreshed is not summary


def test_refresh_summary_presentation_returns_plain_presentation_and_preserves_extras(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))

    refreshed = service.refresh_summary_presentation(summary=_summary(), research_context=_research_context())
    presentation = refreshed["report_presentation"]

    assert isinstance(presentation, dict)
    assert presentation["frontend_extra"] == {"layout": "compact"}
    assert isinstance(presentation["quick_overview"], dict)
    assert isinstance(presentation["summary_bar"], dict)


def test_refresh_summary_presentation_keeps_repair_behavior(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))

    refreshed = service.refresh_summary_presentation(summary=_summary(), research_context=_research_context())
    presentation = refreshed["report_presentation"]

    assert len(presentation["scenario_table"]["rows"]) >= 3
    assert len(presentation["checklist"]["items"]) >= 5
    assert len(presentation["action_table"]["rows"]) >= 2
    assert refreshed["investment_plan"]["action_table"]
    assert refreshed["scenario_matrix"]
    assert refreshed["checklist"]


def test_refresh_summary_presentation_keeps_data_sources_response_level(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))

    refreshed = service.refresh_summary_presentation(summary=_summary(), research_context=_research_context())

    assert "data_sources" not in refreshed
    assert "data_sources" not in refreshed["report_presentation"]


def test_enforce_mandatory_forecast_sections_preserves_unknown_summary_keys(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))
    summary = _summary()
    original = deepcopy(summary)

    enforced, debug = service.enforce_mandatory_forecast_sections(
        symbol="FPT",
        summary=summary,
        research_context=_research_context(),
        warnings=["kept outside summary"],
    )

    assert summary == original
    assert enforced["custom_summary_key"] == {"kept": True}
    assert enforced["mandatory_forecast_sections_validation"] == debug
    assert enforced is not summary


def test_enforce_mandatory_forecast_sections_repairs_sections_and_aliases(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))
    summary = _summary()
    summary["scenarios"] = []
    summary["scenario_matrix"] = []
    summary["checklist"] = []
    summary["action_plan"] = {}

    enforced, debug = service.enforce_mandatory_forecast_sections(
        symbol="FPT",
        summary=summary,
        research_context=_research_context(),
    )
    presentation = enforced["report_presentation"]

    assert len(presentation["scenario_table"]["rows"]) >= 3
    assert len(presentation["checklist"]["items"]) >= 5
    assert len(presentation["action_table"]["rows"]) >= 2
    assert enforced["investment_plan"]["action_table"]
    assert enforced["scenario_matrix"]
    assert enforced["checklist"]
    assert debug["fallback_used"] is True
    assert debug["response_validation_passed"] is True
    assert debug["presentation_after"]["scenarios"] >= 3
    assert debug["presentation_after"]["checklist"] >= 5
    assert debug["presentation_after"]["action_rows"] >= 2


def test_enforce_mandatory_forecast_sections_returns_plain_presentation_and_preserves_extras(tmp_path):
    service = ReportAssemblyService(_settings(tmp_path))

    enforced, _ = service.enforce_mandatory_forecast_sections(
        symbol="FPT",
        summary=_summary(),
        research_context=_research_context(),
    )
    presentation = enforced["report_presentation"]

    assert isinstance(presentation, dict)
    assert presentation["frontend_extra"] == {"layout": "compact"}
    assert isinstance(presentation["scenario_table"], dict)
    assert isinstance(presentation["checklist"], dict)
    assert isinstance(presentation["action_table"], dict)


def test_enforce_mandatory_forecast_sections_writes_scrubbed_debug_artifact(tmp_path):
    service = ReportAssemblyService(
        _settings(
            tmp_path,
            EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        )
    )
    summary = _summary()
    summary["scenarios"] = [{"scenario": "Chưa xác định", "condition": "Authorization: Bearer SHOULD_NOT_LEAK"}]

    service.enforce_mandatory_forecast_sections(
        symbol="FPT",
        summary=summary,
        research_context=_research_context(),
    )

    artifact = tmp_path / "reports" / "debug" / "FPT_mandatory_forecast_sections_validation.json"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "SHOULD_NOT_LEAK" not in text
    assert "Authorization: Bearer" not in text
    assert "response_validation_passed" in text
