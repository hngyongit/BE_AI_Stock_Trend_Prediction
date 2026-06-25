import json

from analyse.config.settings import Settings
from analyse.prompts.report_prompts import build_report_prompt
from analyse.schemas.report import DataSourceStatus
from analyse.services.financial_source_merge_service import FinancialSourceMergeService
from analyse.services.presentation_contract import sanitize_data_source_statuses
from analyse.services.report_presentation_normalizer import ReportPresentationNormalizer
from analyse.services.report_service import ReportService
from analyse.services.summary_service import SummaryService


def _settings(tmp_path=None, **overrides):
    values = {
        "_env_file": None,
        "ENABLE_FINANCIAL_SOURCE_MERGE": True,
        "FINANCIAL_CONFLICT_TOLERANCE_PCT": 5,
        "EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON": False,
        "VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON": False,
    }
    if tmp_path is not None:
        values["REPORT_OUTPUT_DIR"] = str(tmp_path / "reports")
    values.update(overrides)
    return Settings(**values)


def _primary_stock_detail():
    return {
        "symbol": "HPG",
        "exchange": "HOSE",
        "company": "CTCP Tập đoàn Hòa Phát",
        "financials": {
            "source": "Vietstock Finance BCTC",
            "periods": [
                {
                    "period": "Q1/2026",
                    "year": 2026,
                    "quarter": 1,
                    "revenue": 1000,
                    "profit_after_tax": 100,
                    "total_assets": 5000,
                    "equity": 2500,
                }
            ],
        },
        "data_quality": {"financials_loaded": True, "financial_periods_count": 1, "missing_fields": []},
    }


def _cafef_payload():
    return {
        "source": "CafeF tài chính",
        "source_url": "https://cafef.vn/du-lieu/hose/hpg-tai-chinh.chn",
        "status": "success",
        "periods": [
            {
                "period": "Q1/2026",
                "year": 2026,
                "quarter": 1,
                "revenue": 1100,
                "profit_after_tax": 130,
                "operating_cash_flow": 321,
                "short_term_debt": 222,
                "total_assets": 5005,
            },
            {
                "period": "Q4/2025",
                "year": 2025,
                "quarter": 4,
                "revenue": 900,
                "profit_after_tax": 80,
                "total_assets": 4900,
                "equity": 2400,
            },
        ],
    }


def test_cafef_backfills_missing_metric_without_overwriting_primary(tmp_path):
    merged, report = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [_cafef_payload()],
        symbol="HPG",
        exchange="HOSE",
    )

    latest = merged["financials"]["periods"][0]
    assert latest["revenue"] == 1000
    assert latest["operating_cash_flow"] == 321
    assert latest["short_term_debt"] == 222
    assert latest["_field_sources"]["operating_cash_flow"] == "CafeF tài chính"
    assert any(item["field"] == "operating_cash_flow" for item in report["source_contributions"])


def test_financial_merge_records_conflict_instead_of_overwriting(tmp_path):
    merged, report = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [_cafef_payload()],
        symbol="HPG",
        exchange="HOSE",
    )

    latest = merged["financials"]["periods"][0]
    assert latest["profit_after_tax"] == 100
    assert report["conflicts"]
    conflict = next(item for item in report["conflicts"] if item["field"] == "profit_after_tax")
    assert conflict["secondary_source"] == "CafeF tài chính"
    assert conflict["resolution"] == "kept_primary"


def test_financial_backfill_tracker_records_filled_and_not_filled(tmp_path):
    merged, _ = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [_cafef_payload()],
        symbol="HPG",
        exchange="HOSE",
    )
    tracker = merged["financial_backfill_report"]

    assert tracker["before_backfill"]["missing_fields_count"] >= 2
    assert any(item["field"] == "operating_cash_flow" for item in tracker["backfilled_by_source"])
    assert any(item["field"] == "profit_after_tax" for item in tracker["not_backfilled"])


def test_cafef_financial_status_success_when_contributes_usable_fields(tmp_path):
    merged, report = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [_cafef_payload()],
        symbol="HPG",
        exchange="HOSE",
    )
    service = ReportService(settings=_settings(tmp_path))

    status = service._cafef_financial_status(_cafef_payload(), report["cafef_financial_contribution"])

    assert merged["cafef_financial_contribution"]["filled_fields_count"] > 0
    assert status == "success"


def test_cafef_financial_status_partial_only_when_usable_but_no_fill(tmp_path):
    primary = _primary_stock_detail()
    primary["financials"]["periods"][0]["operating_cash_flow"] = 321
    primary["financials"]["periods"][0]["short_term_debt"] = 222
    cafef = _cafef_payload()
    cafef["periods"] = [cafef["periods"][0]]
    cafef["periods"][0]["revenue"] = 1001
    cafef["periods"][0]["profit_after_tax"] = 101
    merged, report = FinancialSourceMergeService(_settings(tmp_path)).merge(primary, [cafef], symbol="HPG", exchange="HOSE")

    assert merged["cafef_financial_contribution"]["filled_fields_count"] == 0
    assert report["cafef_financial_contribution"]["metrics_count"] > 0
    assert report["cafef_financial_contribution"]["status"] == "partial"


def test_cafef_financial_status_insufficient_when_zero_usable_metrics(tmp_path):
    merged, report = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [{"source": "CafeF tài chính", "status": "insufficient", "periods": []}],
        symbol="HPG",
        exchange="HOSE",
    )

    assert merged["cafef_financial_contribution"]["metrics_count"] == 0
    assert report["cafef_financial_contribution"]["status"] == "insufficient"


def test_cafef_source_name_and_user_facing_detail_are_specific(tmp_path):
    source = DataSourceStatus(
        name="CafeF tài chính",
        type="external_financial",
        status="success",
        detail="filled_count=2; usable_count=8; periods=1; conflicts=1",
    )

    row = sanitize_data_source_statuses([source.model_dump()])[0]

    assert row["name"] == "CafeF tài chính"
    assert row["status"] == "success"
    assert "CafeF đã bù 2 chỉ tiêu" in row["detail"]
    assert "https://" not in row["detail"]
    assert "page.goto" not in row["detail"]


def test_backfilled_fields_render_in_financial_table_and_coverage(tmp_path):
    merged, _ = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [_cafef_payload()],
        symbol="HPG",
        exchange="HOSE",
    )
    summary = SummaryService(settings=_settings(tmp_path)).build_summary(symbol="HPG", stock_detail=merged)
    presentation = ReportPresentationNormalizer(settings=_settings(tmp_path)).normalize(summary)

    row_keys = {row["key"] for row in presentation["financial_table"]["rows"]}
    coverage_keys = {item["key"]: item for item in presentation["data_coverage"]["items"]}

    assert "operating_cash_flow" in row_keys
    assert "cafef_financial" in coverage_keys
    assert coverage_keys["cafef_financial"]["status"] == "success"
    assert "Bổ sung" in coverage_keys["cafef_financial"]["value"]


def test_llm_prompt_input_includes_merged_financials_and_contributions(tmp_path):
    merged, _ = FinancialSourceMergeService(_settings(tmp_path)).merge(
        _primary_stock_detail(),
        [_cafef_payload()],
        symbol="HPG",
        exchange="HOSE",
    )
    summary = SummaryService(settings=_settings(tmp_path)).build_summary(symbol="HPG", stock_detail=merged)
    prompt = build_report_prompt({"symbol": "HPG", "summary": summary}, schema={})

    assert "financials_merged" in prompt
    assert "financial_source_contributions" in prompt
    assert "cafef_financial_contribution" in prompt
    assert "CafeF tài chính" in prompt


def test_financial_backfill_debug_artifact_does_not_expose_secrets(tmp_path):
    settings = _settings(tmp_path, EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True, FINANCIAL_BACKFILL_WRITE_DEBUG=True)
    payload = _cafef_payload()
    payload["source_url"] = "https://cafef.vn/du-lieu/hose/hpg-tai-chinh.chn?api_key=SECRET"

    FinancialSourceMergeService(settings).merge(_primary_stock_detail(), [payload], symbol="HPG", exchange="HOSE")

    artifact = tmp_path / "reports" / "debug" / "HPG_financial_backfill_report.json"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "SECRET" not in text
    assert "api_key" not in text.lower()
    assert json.loads(text)["backfilled_by_source"]
