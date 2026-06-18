from __future__ import annotations

from analyse.research.base import BaseResearchAdapter
from analyse.schemas.research import ResearchItem


class GoogleNewsResearchAdapter(BaseResearchAdapter):
    source_name = "Google News RSS"

    async def search(self, symbol: str, company: str | None = None) -> list[ResearchItem]:
        # TODO: Lấy Google News RSS, cache XML và chuẩn hóa item.
        return []
