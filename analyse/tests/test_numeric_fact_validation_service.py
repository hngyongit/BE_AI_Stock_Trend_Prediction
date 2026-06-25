from __future__ import annotations

import json

from analyse.services.numeric_fact_validation_service import NumericFactValidationService


def _service() -> NumericFactValidationService:
    return NumericFactValidationService()


def _summary() -> dict:
    return {
        "symbol": "FPT",
        "latest_market": {"close_price": 100.0, "volume": 1_200_000, "pe": 10.0, "pb": 2.0, "roe": 20.0},
        "scores": {"overall_score": 71, "risk_score": 42, "score_confidence": 0.72},
        "investment_plan": {"position_sizing": {"max_position_pct": 12, "risk_per_trade_pct": 1}},
        "bctc_3q": {
            "source": "Vietstock Finance BCTC",
            "periods": [
                {"period": "Q2/2026", "revenue": 1200, "profit_after_tax": 210, "gross_margin": 33.3},
                {"period": "Q1/2026", "revenue": 1000, "profit_after_tax": 180, "gross_margin": 32.0},
            ],
        },
        "strengths": ["Doanh thu cải thiện và biên lợi nhuận ổn định."],
        "weaknesses": ["Rủi ro thị trường chung cần theo dõi."],
        "action_plan": {
            "short_term": [
                {
                    "action": "Theo dõi thanh khoản.",
                    "condition": "Chỉ nâng mức đánh giá khi dữ liệu xác nhận.",
                    "price_zone": None,
                    "position_size_note": "Không vượt quá 12% danh mục giả định.",
                    "risk_note": "Rủi ro tham chiếu 1% vốn.",
                }
            ]
        },
        "forecast_scenarios": [
            {"scenario": "Tích cực", "probability_pct": 30, "condition": "Thanh khoản cải thiện."},
            {"scenario": "Cơ sở", "probability_pct": 45, "condition": "Giá đi ngang."},
            {"scenario": "Thận trọng", "probability_pct": 25, "condition": "Rủi ro tăng."},
        ],
        "scenario_matrix": [
            {"scenario": "Tích cực", "probability_pct": 30, "condition": "Thanh khoản cải thiện."},
            {"scenario": "Cơ sở", "probability_pct": 45, "condition": "Giá đi ngang."},
            {"scenario": "Thận trọng", "probability_pct": 25, "condition": "Rủi ro tăng."},
        ],
        "checklist": [
            {"label": "Đọc BCTC", "note": "So sánh doanh thu và lợi nhuận với kỳ trước.", "source_basis": "BCTC"},
            {"label": "Kiểm tra thanh khoản", "note": "Đối chiếu khối lượng giao dịch.", "source_basis": "Dữ liệu giá"},
        ],
        "report_presentation": {
            "financial_table": {
                "rows": [
                    {"metric": "Doanh thu", "raw_values": [1200, 1000], "values": ["1.200", "1.000"]},
                    {"metric": "Lợi nhuận sau thuế", "raw_values": [210, 180], "values": ["210", "180"]},
                ]
            },
            "action_table": {
                "rows": [
                    {
                        "timeframe": "Ngắn hạn",
                        "action": "Theo dõi thanh khoản.",
                        "condition": "Dữ liệu mới xác nhận.",
                        "price_zone": "Theo vùng giá hiện tại.",
                        "position_size": "Không vượt quá 12% danh mục giả định.",
                        "stop_loss": "Theo nguyên tắc rủi ro 1% vốn.",
                    }
                ]
            },
            "scenario_table": {"rows": []},
            "checklist": {"items": []},
            "quick_overview": {"cards": [{"label": "Giá", "raw_value": 100.0, "value": "100"}]},
            "market_context_view": {"cards": []},
            "data_coverage": {"items": []},
        },
    }


def _source_payload() -> dict:
    summary = _summary()
    return {
        "stock_detail": {
            "latest_market": summary["latest_market"],
            "financials": summary["bctc_3q"],
            "scores": summary["scores"],
            "investment_plan": summary["investment_plan"],
        },
        "financials": summary["bctc_3q"],
    }


def test_source_backed_numeric_values_are_preserved():
    summary = _summary()
    summary["llm_quantitative_signal_summary"] = {
        "overall_score": 71,
        "comment": "Điểm tổng 71/100 và ROE 20% đã có trong dữ liệu nguồn.",
    }

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())

    assert result.payload["llm_quantitative_signal_summary"]["overall_score"] == 71
    assert "71/100" in result.payload["llm_quantitative_signal_summary"]["comment"]
    assert result.issues == []


def test_backend_financial_table_numeric_rows_are_preserved():
    summary = _summary()

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())

    table = result.payload["report_presentation"]["financial_table"]
    assert table["rows"][0]["raw_values"] == [1200, 1000]
    assert table["rows"][1]["raw_values"] == [210, 180]
    assert result.issues == []


def test_llm_narrative_with_unsupported_exact_target_price_is_flagged():
    summary = _summary()
    summary["strengths"].append("Giá mục tiêu 125,000 VND cho thấy upside hấp dẫn.")

    result = _service().validate_summary(summary=summary, source_payload={"stock_detail": {"latest_market": {"close_price": 100}}})

    text = " ".join(result.payload["strengths"])
    assert "125,000" not in text
    assert "số liệu cần kiểm chứng" in text
    assert result.issues
    assert result.warnings


def test_llm_narrative_with_unsupported_revenue_or_profit_figure_is_flagged():
    summary = _summary()
    summary["data_quality_notes"] = ["Doanh thu đạt 9.876 tỷ và lợi nhuận sau thuế 777 tỷ theo mô hình."]

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())

    note = result.payload["data_quality_notes"][0]
    assert "9.876" not in note
    assert "777" not in note
    assert note.count("số liệu cần kiểm chứng") >= 2


def test_qualitative_scenario_checklist_action_text_is_preserved():
    summary = _summary()

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())

    assert result.payload["forecast_scenarios"][0]["condition"] == "Thanh khoản cải thiện."
    assert result.payload["checklist"][0]["note"] == "So sánh doanh thu và lợi nhuận với kỳ trước."
    assert result.payload["action_plan"]["short_term"][0]["action"] == "Theo dõi thanh khoản."


def test_scenario_probabilities_from_existing_policy_are_preserved_but_llm_raw_probabilities_are_validated():
    summary = _summary()
    summary["llm_scenarios"] = [{"scenario": "Tích cực", "probability_pct": 63, "condition": "Xác suất 63% nếu doanh thu cải thiện."}]

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())

    assert [row["probability_pct"] for row in result.payload["scenario_matrix"]] == [30, 45, 25]
    assert result.payload["llm_scenarios"][0]["probability_pct"] is None
    assert "63%" not in result.payload["llm_scenarios"][0]["condition"]


def test_unsupported_numeric_value_field_is_set_to_null():
    summary = _summary()
    summary["action_plan"]["short_term"][0]["price_zone"] = 125000

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())

    assert result.payload["action_plan"]["short_term"][0]["price_zone"] is None
    assert any(issue.path.endswith("price_zone") and issue.action == "set_null" for issue in result.issues)


def test_validation_returns_plain_dict_list_primitives():
    result = _service().validate_summary(summary=_summary(), source_payload=_source_payload())

    json.dumps(result.payload, ensure_ascii=False)
    assert isinstance(result.payload, dict)
    assert isinstance(result.payload["report_presentation"]["financial_table"]["rows"], list)


def test_debug_payload_is_scrubbed():
    summary = _summary()
    summary["strengths"].append("Authorization: Bearer SHOULD_NOT_LEAK với giá mục tiêu 125000 VND.")

    result = _service().validate_summary(summary=summary, source_payload=_source_payload())
    debug_payload = _service().build_debug_payload(symbol="FPT", result=result)
    serialized = json.dumps(debug_payload, ensure_ascii=False)

    assert "SHOULD_NOT_LEAK" not in serialized
    assert "Authorization: Bearer" not in serialized
    assert debug_payload["issue_count"] == 1
