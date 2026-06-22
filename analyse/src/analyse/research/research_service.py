from __future__ import annotations

from datetime import datetime

from analyse.config.settings import Settings, get_settings
from analyse.research.cafef import CafeFResearchAdapter
from analyse.research.google_news import GoogleNewsResearchAdapter
from analyse.research.base import normalize_domain
from analyse.research.base import parse_datetime_for_sort
from analyse.research.vietstock import VietstockResearchAdapter
from analyse.schemas.research import ExternalResearchContext, ResearchItem


class ExternalResearchService:
    """Orchestrator lấy dữ liệu nghiên cứu bên ngoài."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.source_priority = self._parse_source_priority(self.settings.research_source_priority)

    async def search(self, symbol: str, company: str | None = None) -> ExternalResearchContext:
        adapters = self._build_adapters()

        if not adapters:
            return ExternalResearchContext(
                enabled=True,
                status="disabled",
                items=[],
                flag_summary={"warnings": ["Không có research adapter nào được bật."]},
                source_statuses=[],
                note="Tin tức bên ngoài chỉ là bằng chứng ngữ cảnh và cần kiểm chứng từ nguồn gốc.",
            )

        items: list[ResearchItem] = []
        warnings: list[str] = []
        source_statuses: list[dict] = []
        for adapter in adapters:
            try:
                adapter_items = await adapter.search(symbol=symbol, company=company)
                items.extend(adapter_items)
                source_statuses.append(
                    {
                        "name": adapter.source_name,
                        "status": "success" if adapter_items else "partial",
                        "items": len(adapter_items),
                    }
                )
            except Exception as exc:
                warning = f"{adapter.source_name}: {exc}"
                warnings.append(warning)
                source_statuses.append({"name": adapter.source_name, "status": "failed", "items": 0, "detail": str(exc)})

        sorted_items = self._sort_and_limit(self._deduplicate(items))
        status = "success" if sorted_items and not warnings else "partial" if sorted_items or warnings or source_statuses else "failed"
        return ExternalResearchContext(
            enabled=True,
            status=status,
            items=sorted_items,
            flag_summary=self._build_flag_summary(sorted_items, warnings),
            source_statuses=source_statuses,
            note="Tin tức/nghiên cứu bên ngoài chỉ là bằng chứng ngữ cảnh; cần mở URL gốc để kiểm chứng trước khi ra quyết định.",
        )

    def _build_adapters(self):
        adapters = []
        if self.settings.enable_vietstock:
            adapters.append(VietstockResearchAdapter(self.settings))
        if self.settings.enable_cafef:
            adapters.append(CafeFResearchAdapter(self.settings))
        if self.settings.enable_google_news_rss and self.settings.research_google_news_rss_enabled:
            adapters.append(GoogleNewsResearchAdapter(self.settings))
        return adapters

    def _parse_source_priority(self, value: str) -> list[str]:
        return [normalize_domain(item.strip()) for item in value.split(",") if item.strip()]

    def _deduplicate(self, items: list[ResearchItem]) -> list[ResearchItem]:
        result: list[ResearchItem] = []
        seen: set[str] = set()
        for item in items:
            key = item.url or item.title or ""
            key = key.strip().lower()
            if not key or key in seen:
                continue
            result.append(item)
            seen.add(key)
        return result

    def _sort_and_limit(self, items: list[ResearchItem]) -> list[ResearchItem]:
        return sorted(items, key=self._sort_key, reverse=True)[: self.settings.max_research_items]

    def _sort_key(self, item: ResearchItem) -> tuple[float, int, datetime]:
        relevance = item.relevance_score or 0.0
        priority = self._source_priority_score(item)
        published = parse_datetime_for_sort(item.published_at) or datetime.min
        return (relevance, priority, published.replace(tzinfo=None))

    def _source_priority_score(self, item: ResearchItem) -> int:
        url_domain = normalize_domain(item.url)
        source = (item.source or "").lower()
        for index, domain in enumerate(self.source_priority):
            if domain and (domain in url_domain or domain.replace(".vn", "") in source):
                return len(self.source_priority) - index
        return 0

    def _build_flag_summary(self, items: list[ResearchItem], warnings: list[str]) -> dict:
        summary = {
            "positive_flags": sorted({flag for item in items for flag in item.positive_flags}),
            "negative_flags": sorted({flag for item in items for flag in item.negative_flags}),
            "catalyst_flags": sorted({flag for item in items for flag in item.catalyst_flags}),
        }
        if warnings:
            summary["warnings"] = warnings
        return summary
