from __future__ import annotations

import asyncio

from analyse.config.settings import Settings
from analyse.schemas.research import ExternalResearchContext, ResearchItem
from analyse.services.source_collection_coordinator import SourceCollectionCoordinator


class FakeSourceBackedEnrichmentService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def enrich(
        self,
        *,
        symbol: str,
        exchange: str | None,
        company_name: str | None,
        summary: dict,
        research_context: ExternalResearchContext | None,
    ) -> dict:
        self.calls.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "company_name": company_name,
                "summary": summary,
                "research_context": research_context,
            }
        )
        enriched = dict(summary)
        enriched["source_backed_evidence"] = {
            "sources_successful": ["CafeF"],
            "warnings": ["Một cảnh báo nguồn đã được giữ lại."],
        }
        enriched["evidence_table"] = [
            {
                "source_name": "CafeF",
                "source_type": "news",
                "title": "FPT lợi nhuận tăng",
                "url": "https://cafef.vn/fpt.html",
            }
        ]
        enriched["report_presentation"] = {
            "research_insights": {
                "positive_catalysts": ["Tin lợi nhuận tăng"],
                "risks": [],
            }
        }
        return enriched


def _settings(tmp_path):
    return Settings(
        ENABLE_EXTERNAL_RESEARCH=False,
        ENABLE_DEEP_RESEARCH_CRAWL=False,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
    )


def _research_context() -> ExternalResearchContext:
    return ExternalResearchContext(
        enabled=True,
        status="success",
        items=[
            ResearchItem(
                source="CafeF",
                type="google_news_rss",
                title="FPT lợi nhuận tăng",
                url="https://cafef.vn/fpt.html",
                snippet="FPT ghi nhận lợi nhuận tăng.",
                relevance_score=0.9,
            )
        ],
    )


def test_collect_source_backed_enrichment_calls_service_with_expected_inputs(tmp_path):
    fake_service = FakeSourceBackedEnrichmentService()
    coordinator = SourceCollectionCoordinator(
        _settings(tmp_path),
        source_backed_enrichment_service=fake_service,
    )
    summary = {
        "symbol": "FPT",
        "company": "CTCP FPT",
        "external_research_context": {"enabled": True, "status": "success", "items": []},
    }
    research_context = _research_context()

    result = asyncio.run(
        coordinator.collect_source_backed_enrichment(
            symbol="FPT",
            exchange="HOSE",
            stock_payload={"company": "CTCP FPT"},
            company_name="CTCP FPT",
            summary=summary,
            research_context=research_context,
            token="request-token",
            options={"includeExternalResearch": True},
        )
    )

    assert fake_service.calls == [
        {
            "symbol": "FPT",
            "exchange": "HOSE",
            "company_name": "CTCP FPT",
            "summary": summary,
            "research_context": research_context,
        }
    ]
    assert result.enriched_summary is not None
    assert result.enriched_summary["source_backed_evidence"]["sources_successful"] == ["CafeF"]
    assert result.source_backed_context == result.enriched_summary["source_backed_evidence"]
    assert result.evidence_table == result.enriched_summary["evidence_table"]
    assert result.source_backed_warnings == ["Một cảnh báo nguồn đã được giữ lại."]
    assert result.research_insights == {
        "positive_catalysts": ["Tin lợi nhuận tăng"],
        "risks": [],
    }


def test_collect_source_backed_enrichment_infers_company_name_when_not_provided(tmp_path):
    fake_service = FakeSourceBackedEnrichmentService()
    coordinator = SourceCollectionCoordinator(
        _settings(tmp_path),
        source_backed_enrichment_service=fake_service,
    )

    asyncio.run(
        coordinator.collect_source_backed_enrichment(
            symbol="FPT",
            exchange="HOSE",
            stock_payload={"company_overview": {"company_name": "CTCP FPT"}},
            summary={"symbol": "FPT"},
            research_context=_research_context(),
        )
    )

    assert fake_service.calls[0]["company_name"] == "CTCP FPT"
