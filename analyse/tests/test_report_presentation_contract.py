from __future__ import annotations

from copy import deepcopy

from analyse.schemas.common import api_success
from analyse.schemas.report_presentation import ReportPresentation
from analyse.services.report_presentation_contract_service import ReportPresentationContractService


def _service() -> ReportPresentationContractService:
    return ReportPresentationContractService()


def test_report_presentation_accepts_existing_dict_with_extra_keys():
    payload = {
        "quick_overview": {"cards": [{"label": "Giá", "value": 100, "frontend_only": True}]},
        "market_context_view": {"cards": []},
        "financial_table": {"columns": ["Chỉ tiêu"], "rows": []},
        "valuation": "Chưa đủ dữ liệu định giá xác thực.",
        "custom_frontend_section": {"enabled": True},
    }

    dumped = ReportPresentation.model_validate(payload).model_dump(mode="json")

    assert isinstance(dumped, dict)
    assert dumped["quick_overview"]["cards"][0]["frontend_only"] is True
    assert dumped["valuation"] == "Chưa đủ dữ liệu định giá xác thực."
    assert dumped["custom_frontend_section"] == {"enabled": True}


def test_contract_service_preserves_unknown_frontend_keys_and_plain_dict_output():
    payload = {
        "quick_overview": {"cards": [{"label": "Giá", "value": 100}]},
        "market_context_view": {"cards": []},
        "financial_table": {"rows": [], "columns": []},
        "action_table": {"rows": []},
        "scenario_table": {"rows": []},
        "checklist": {"items": []},
        "data_coverage": {"items": []},
        "frontend_extra": {"layout": "compact"},
    }

    result = _service().normalize_and_validate(payload)

    assert isinstance(result, dict)
    assert result["frontend_extra"] == {"layout": "compact"}
    assert isinstance(result["quick_overview"], dict)
    assert isinstance(result["scenario_table"]["rows"], list)


def test_missing_scenario_table_rows_are_repaired():
    result = _service().normalize_and_validate({"scenario_table": {"rows": []}})

    rows = result["scenario_table"]["rows"]
    assert len(rows) >= 3
    assert {row["scenario"] for row in rows[:3]} == {"Tích cực", "Cơ sở", "Thận trọng"}
    assert result["scenario_table"]["status"] == "available"


def test_missing_checklist_items_are_repaired():
    result = _service().normalize_and_validate({"checklist": {"items": []}})

    items = result["checklist"]["items"]
    assert len(items) >= 5
    assert all(item["status"] == "pending" for item in items[:5])
    assert result["checklist"]["status"] == "available"


def test_missing_action_table_rows_are_repaired():
    result = _service().normalize_and_validate({"action_table": {"rows": []}})

    rows = result["action_table"]["rows"]
    assert len(rows) >= 2
    assert all(row["action"] for row in rows[:2])
    assert result["action_table"]["status"] == "available"


def test_data_coverage_never_returns_available_with_unverified_value():
    payload = {
        "data_coverage": {
            "items": [
                {
                    "key": "market_data",
                    "title": "Giá và thanh khoản",
                    "status": "available",
                    "status_label": "Đã ghi nhận",
                    "value": "Chưa xác minh",
                }
            ]
        }
    }

    result = _service().normalize_and_validate(payload)
    item = result["data_coverage"]["items"][0]

    assert not (item["status"] == "available" and item["value"] == "Chưa xác minh")
    assert item["status"] == "missing"
    assert result["coverage_rows"][0]["status"] == "missing"


def test_invalid_section_type_is_normalized_safely():
    payload = {
        "quick_overview": "bad-card",
        "market_context_view": {"cards": "bad-market-card"},
        "scenario_table": "bad-scenario",
        "checklist": {"items": "bad-checklist"},
        "action_table": {"rows": {"action": "Theo dõi"}},
        "data_coverage": "bad-coverage",
    }

    result = _service().normalize_and_validate(payload)

    assert isinstance(result["quick_overview"]["cards"], list)
    assert isinstance(result["market_context_view"]["cards"], list)
    assert len(result["scenario_table"]["rows"]) >= 3
    assert len(result["checklist"]["items"]) >= 5
    assert len(result["action_table"]["rows"]) >= 2
    assert isinstance(result["data_coverage"]["items"], list)


def test_contract_service_does_not_mutate_input_object():
    payload = {
        "scenario_table": {"rows": []},
        "checklist": {"items": []},
        "action_table": {"rows": []},
        "data_coverage": {"items": [{"title": "Watchlist", "status": "available", "value": "Chưa xác minh"}]},
    }
    original = deepcopy(payload)

    _service().normalize_and_validate(payload)

    assert payload == original


def test_final_response_envelope_remains_code_message_data():
    presentation = _service().normalize_and_validate({"scenario_table": {"rows": []}})
    response = api_success("ok", data={"summary": {"report_presentation": presentation}})

    assert set(response.keys()) == {"code", "message", "data"}
    assert isinstance(response["data"]["summary"]["report_presentation"], dict)
