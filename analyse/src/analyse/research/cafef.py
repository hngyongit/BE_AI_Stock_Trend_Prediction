from __future__ import annotations

from analyse.research.base import BaseResearchAdapter
from analyse.schemas.research import ResearchItem


class CafeFResearchAdapter(BaseResearchAdapter):
    source_name = "CafeF"

    async def search(self, symbol: str, company: str | None = None) -> list[ResearchItem]:
        # TODO: Lấy tin public/RSS từ CafeF nếu hợp lệ.
        return []
