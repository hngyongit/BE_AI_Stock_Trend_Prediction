from __future__ import annotations

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings
from analyse.research.google_news import GoogleNewsResearchAdapter


class VietstockResearchAdapter(GoogleNewsResearchAdapter):
    source_name = "Vietstock"

    def __init__(self, settings: Settings | None = None, http_client: HttpClient | None = None) -> None:
        super().__init__(
            settings=settings,
            http_client=http_client,
            source_name="Vietstock",
            source_type="vietstock_via_google_news_rss",
            domain_filter="vietstock.vn",
            query_suffixes=["Vietstock", "phân tích Vietstock", "tin doanh nghiệp Vietstock"],
        )
