from __future__ import annotations

import json
from datetime import date, timedelta

from analyse.config.settings import Settings
from analyse.services.visualization_dataset_service import VisualizationDatasetService


def _price_rows(count: int = 60) -> list[dict]:
    start = date(2024, 1, 1)
    rows = []
    for idx in range(count):
        close = 100.0 + idx
        rows.append(
            {
                "time": (start + timedelta(days=idx)).isoformat(),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + idx * 10,
            }
        )
    return rows


def _report_response(
    price_history: list[dict] | None = None,
    financial_periods: list[dict] | None = None,
    peers: list[dict] | None = None,
    market_context: dict | None = None,
) -> dict:
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "report_id": "UNIT_HOSE_report",
            "generated_at": "2024-03-01T09:00:00+07:00",
            "symbol": "UNIT",
            "scope_exchange": "HOSE",
            "provider": {"name": "openai", "model": "test-model", "status": "success"},
            "data_sources": [{"name": "Backend /api/stocks/:symbol/analysis-data", "type": "backend_api", "status": "success"}],
            "warnings": ["Authorization: Bearer secret-token", "OPENAI_API_KEY=sk-secret-value"],
            "summary": {
                "price_history": price_history if price_history is not None else _price_rows(),
                "bctc_3q": {
                    "periods": financial_periods
                    if financial_periods is not None
                    else [
                        {"period": "Q1/2024", "year": 2024, "quarter": 1, "revenue": 1000, "gross_profit": 300, "profit_after_tax": 120, "parent_profit": 110, "eps": 10, "roe": 15, "roaa": 5, "total_assets": 3000, "total_liabilities": 1200, "equity": 1800},
                        {"period": "Q2/2024", "year": 2024, "quarter": 2, "revenue": 1100, "gross_profit": 330, "profit_after_tax": 130, "parent_profit": 125, "eps": 11, "roe": 16, "roa": 5.5, "total_assets": 3200, "total_liabilities": 1280, "equity": 1920},
                    ]
                },
                "scores": {"overall_score": 72, "valuation_score": 68, "risk_score": 41, "score_confidence": 0.8},
                "score_explanations": {"overall_score": ["Fixture score explanation"]},
                "industry_peer_context": {
                    "industry": {"sector": "Technology", "industry": "Software"},
                    "peers": peers if peers is not None else [{"symbol": "PEER", "exchange": "HOSE", "market_cap": 2000, "pe": 12, "pb": 2, "roe": 18}],
                },
                "hose_market_context": market_context if market_context is not None else {"index_symbol": "VNINDEX", "vnindex": 1200, "change_percent": 0.5, "market_health_score": 61},
                "strengths": ["Nền tảng dữ liệu fixture đủ để kiểm thử."],
                "weaknesses": ["=formula-like risk"],
                "scenarios": [{"scenario": "base", "expected_behavior": "Theo dõi tiếp", "probability_pct": 50}],
                "action_plan": {"short_term": [{"action": "Quan sát", "condition": "Không hành động nếu thiếu dữ liệu"}]},
                "checklist": [{"label": "Kiểm tra dữ liệu", "status": "pending", "note": "Đối chiếu nguồn"}],
                "evidence_table": [{"source": "fixture", "fact": "Có dữ liệu test"}],
                "data_quality": {"missing_fields": [], "warnings": ["GEMINI_API_KEY=AIza-secret-value"], "units": {"price": "VND"}},
                "data_coverage": {"price_history_points": len(price_history if price_history is not None else _price_rows()), "financial_periods_count": 2},
            },
        },
    }


def _table(dataset, name: str):
    return next(table for table in dataset.tables if table.name == name)


def test_visualization_prices_table_preserves_ohlcv_and_adds_derived_metadata():
    service = VisualizationDatasetService(Settings(_env_file=None, VISUALIZATION_MAX_ROWS=5000))
    dataset = service.build_from_report_response(_report_response(), chart_range="1y")

    prices = _table(dataset, "prices")
    assert prices.row_count == 60
    assert prices.rows[0]["open"] == 99.0
    assert prices.rows[0]["high"] == 102.0
    assert prices.rows[0]["low"] == 98.0
    assert prices.rows[0]["close"] == 100.0
    assert prices.rows[0]["volume"] == 1000.0
    column_meta = {column.name: column for column in prices.columns}
    assert column_meta["ma20"].derived is True
    assert column_meta["ma20"].required_history_points == 20
    assert column_meta["return_pct"].formula
    assert "rsi_14" in column_meta
    assert "macd" in column_meta
    assert any(row["ma20"] is not None for row in prices.rows)


def test_visualization_missing_price_history_returns_valid_empty_prices_table():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response(price_history=[]))

    prices = _table(dataset, "prices")
    assert prices.row_count == 0
    assert [column.name for column in prices.columns][:6] == ["date", "open", "high", "low", "close", "volume"]


def test_visualization_financial_table_handles_missing_financials():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response(financial_periods=[]))

    financials = _table(dataset, "financial_periods")
    assert financials.row_count == 0
    assert any(column.name == "debt_to_equity" and column.derived for column in financials.columns)


def test_visualization_financial_table_derives_debt_to_equity_when_possible():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response())

    financials = _table(dataset, "financial_periods")
    assert financials.rows[0]["debt_to_equity"] == 0.6667


def test_visualization_dataset_scrubs_secret_markers_from_response():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response())
    serialized = json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False)

    assert "Authorization" not in serialized
    assert "Bearer" not in serialized
    assert "secret-token" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "GEMINI_API_KEY" not in serialized
    assert "sk-secret-value" not in serialized
    assert "AIza-secret-value" not in serialized


def test_visualization_csv_export_sanitizes_formula_like_cells():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response())

    csv_text = service.table_to_csv(dataset, "ai_signals")

    assert "'=formula-like risk" in csv_text


def test_data_formulator_package_contains_fast_csv_table_metadata(tmp_path):
    service = VisualizationDatasetService(Settings(_env_file=None, DATA_FORMULATOR_HOME=str(tmp_path)))
    dataset = service.build_from_report_response(_report_response())

    package = service.build_data_formulator_package(dataset)

    assert package["schema_version"] == "data_formulator.v1"
    assert package["report_id"] == "UNIT_HOSE_report"
    assert package["recommended_start_table"] == "prices"
    assert {table["name"] for table in package["tables"]} == {"prices", "financial_periods"}
    assert all(table["filename"].endswith(".csv") for table in package["tables"])


def test_visualization_v2_contains_chart_first_payload_without_warning_blocks():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response())

    visualization = dataset.visualization

    assert visualization["schema_version"] == "visualization.v2"
    assert isinstance(visualization["charts"], list)
    assert visualization["charts"]
    assert "warnings" not in visualization
    assert "missingFields" not in visualization
    assert "missing_fields" not in visualization


def test_price_volume_chart_has_separate_price_and_volume_grids():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response())

    chart = next(chart for chart in dataset.visualization["charts"] if chart["id"] == "price_volume")
    option = chart["option"]

    assert len(option["grid"]) == 2
    assert len(option["xAxis"]) == 2
    assert len(option["yAxis"]) == 2
    volume_series = next(series for series in option["series"] if series["name"] == "Khối lượng")
    assert volume_series["xAxisIndex"] == 1
    assert volume_series["yAxisIndex"] == 1


def test_empty_peer_and_market_data_do_not_create_fake_charts():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response(peers=[], market_context={}))
    chart_ids = {chart["id"] for chart in dataset.visualization["charts"]}

    assert "peer_comparison" not in chart_ids
    assert "market_context" not in chart_ids
    omitted_ids = {item["id"] for item in dataset.visualization["meta"]["omitted_charts"]}
    assert "peer_comparison" in omitted_ids
    assert "market_context" in omitted_ids


def test_chart_builder_error_omits_only_that_chart(monkeypatch):
    service = VisualizationDatasetService(Settings(_env_file=None))

    def raise_peer_error(rows):
        raise RuntimeError("peer chart broke")

    monkeypatch.setattr(service, "_peer_chart", raise_peer_error)
    dataset = service.build_from_report_response(_report_response())
    chart_ids = {chart["id"] for chart in dataset.visualization["charts"]}
    omitted = dataset.visualization["meta"]["omitted_charts"]

    assert "price_volume" in chart_ids
    assert "peer_comparison" not in chart_ids
    assert any(item["id"] == "peer_comparison" for item in omitted)


def test_scores_chart_is_omitted_when_scores_are_not_meaningful():
    service = VisualizationDatasetService(Settings(_env_file=None))
    dataset = service.build_from_report_response(_report_response())
    chart_ids = {chart["id"] for chart in dataset.visualization["charts"]}

    assert "scores" not in chart_ids
