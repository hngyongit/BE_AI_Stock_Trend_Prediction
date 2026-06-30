# Analyse Test Index

## 1. Full test command

```powershell
cd analyse
uv run python -m compileall src
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest -q
```

## 2. Core API contract tests

- `tests/test_endpoint_contract.py`
- `tests/test_analyse_one_flow.py`

Use these when changing routes, `ReportService.analyse_one_report()`, response envelope, watchlist/auth flow, provider metadata, source status or history status in `analyse-one`.

## 3. Report presentation tests

- `tests/test_report_presentation_contract.py`
- `tests/test_report_presentation_missing_fields.py`
- `tests/test_report_renderers.py`
- `tests/test_presentation_contract.py`
- `tests/test_report_schema.py`

Use these when changing `report_presentation`, renderer input shape, mandatory scenario/checklist/action sections, source labels or report schemas.

## 4. Debug/secret scrub tests

- `tests/test_debug_scrub.py`
- `tests/test_report_debug_service.py`
- `tests/test_visualization_dataset_service.py`

Use these when adding debug artifacts, changing scrub logic, changing URL/DB masking, visualization export payloads, CSV export, or moving writer boundaries.

## 5. Source/crawler tests

- `tests/test_cafef_adapters.py`
- `tests/test_vietstock_financial_adapter.py`
- `tests/test_vietstock_peer_adapter.py`
- `tests/test_playwright_safe.py`
- `tests/test_financial_source_merge_service.py`
- `tests/test_peer_enrichment.py`
- `tests/test_source_backed_research_pipeline.py`
- `tests/test_source_collection_coordinator.py`
- `tests/test_source_collection_source_backed.py`
- `tests/test_external_research.py`

Use these when changing Backend source loading, CafeF/Vietstock adapters, Playwright cleanup, financial backfill, peer enrichment or external research.

## 6. LLM/numeric validation tests

- `tests/test_numeric_fact_validation_service.py`
- `tests/test_force_llm_forecast_sections.py`
- `tests/test_provider_factory.py`
- `tests/test_report_assembly_service.py`

Use these when changing LLM provider selection, LLM output merge, numeric guardrails, mandatory forecast repair, scenario/action/checklist handling or assembly helpers.

## 7. SQL history tests

- `tests/test_ai_report_history.py`
- `tests/test_analyse_one_flow.py`
- `tests/test_endpoint_contract.py`

Use these when changing history settings, SQL repository behavior, history endpoints, non-blocking/strict save policy or `created_at` expectations.

## 8. Settings/config tests

- `tests/test_settings.py`
- `tests/test_backend_client.py`
- `tests/test_asyncio_windows.py`
- `tests/test_datetime_utils.py`
- `tests/test_report_file_service.py`
- `tests/test_report_status_service.py`
- `tests/test_summary_scoring.py`
- `tests/test_phase5_service_skeletons.py`

Use these for settings aliases, config diagnostics, Backend client behavior, Windows async helpers, report file writes, report status logic, scoring and service skeleton compatibility.

## 8A. Visualization/Data Formulator tests

- `tests/test_visualization_dataset_service.py`
- `tests/test_visualization_routes.py`

Use these when changing `visualization.v1`, chart-ready tables, derived indicators, JSON/CSV export routes, feature flags, or Data Formulator sidecar setup.

## 9. Recommended test commands by change type

API contract:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_endpoint_contract.py tests/test_analyse_one_flow.py -q
```

Presentation/rendering:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_report_presentation_contract.py tests/test_report_presentation_missing_fields.py tests/test_report_renderers.py -q
```

Debug scrub:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_debug_scrub.py tests/test_report_debug_service.py -q
```

CafeF/Vietstock/Playwright:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_cafef_adapters.py tests/test_vietstock_financial_adapter.py tests/test_vietstock_peer_adapter.py tests/test_playwright_safe.py -q
```

LLM forecast and numeric guardrails:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_numeric_fact_validation_service.py tests/test_force_llm_forecast_sections.py tests/test_report_assembly_service.py -q
```

SQL history:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_ai_report_history.py tests/test_analyse_one_flow.py tests/test_endpoint_contract.py -q
```

Settings/config:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_settings.py tests/test_backend_client.py -q
```

Visualization/Data Formulator:

```powershell
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest tests/test_visualization_dataset_service.py tests/test_visualization_routes.py -q
```

Before final handoff, always run full compile and full pytest.
