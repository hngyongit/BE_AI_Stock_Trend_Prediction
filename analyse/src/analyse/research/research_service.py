from __future__ import annotations

from analyse.config.settings import Settings, get_settings
from analyse.research.cafef import CafeFResearchAdapter
from analyse.research.google_news import GoogleNewsResearchAdapter
from analyse.research.vietstock import VietstockResearchAdapter
from analyse.schemas.research import ExternalResearchContext, ResearchItem


class ExternalResearchService:
    """Orchestrator lấy dữ liệu nghiên cứu bên ngoài."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def search(self, symbol: str, company: str | None = None) -> ExternalResearchContext:
        if not self.settings.enable_external_research:
            return ExternalResearchContext(enabled=False, status="disabled", items=[], flag_summary={})

        adapters = []
        if self.settings.enable_vietstock:
            adapters.append(VietstockResearchAdapter())
        if self.settings.enable_cafef:
            adapters.append(CafeFResearchAdapter())
        if self.settings.enable_google_news_rss:
            adapters.append(GoogleNewsResearchAdapter())

        items: list[ResearchItem] = []
        warnings: list[str] = []
        for adapter in adapters:
            try:
                items.extend(await adapter.search(symbol=symbol, company=company))
            except Exception as exc:  # pragma: no cover
                warnings.append(f"{adapter.source_name}: {exc}")

        status = "success" if items else "partial"
        return ExternalResearchContext(
            enabled=True,
            status=status,
            items=items[: self.settings.max_research_items],
            flag_summary={"warnings": warnings} if warnings else {},
            note="Dữ liệu nghiên cứu bên ngoài chỉ dùng để tham khảo, cần kiểm chứng lại.",
        )
