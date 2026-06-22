from __future__ import annotations

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings
from analyse.research.google_news import GoogleNewsResearchAdapter


class CafeFResearchAdapter(GoogleNewsResearchAdapter):
    source_name = "CafeF"

    def __init__(self, settings: Settings | None = None, http_client: HttpClient | None = None) -> None:
        super().__init__(
            settings=settings,
            http_client=http_client,
            source_name="CafeF",
            source_type="cafef_via_google_news_rss",
            domain_filter="cafef.vn",
            query_suffixes=["CafeF", "kết quả kinh doanh CafeF", "cổ tức CafeF"],
        )
