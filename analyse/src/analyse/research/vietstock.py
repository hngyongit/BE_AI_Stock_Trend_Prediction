from __future__ import annotations

from analyse.research.base import BaseResearchAdapter
from analyse.schemas.research import ResearchItem


class VietstockResearchAdapter(BaseResearchAdapter):
    source_name = "Vietstock"

    async def search(self, symbol: str, company: str | None = None) -> list[ResearchItem]:
        # TODO: Chỉ lấy dữ liệu public hợp lệ, có cache và timeout.
        return []
