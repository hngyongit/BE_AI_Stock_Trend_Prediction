from __future__ import annotations

from abc import ABC, abstractmethod

from analyse.schemas.research import ResearchItem


class BaseResearchAdapter(ABC):
    source_name: str

    @abstractmethod
    async def search(self, symbol: str, company: str | None = None) -> list[ResearchItem]:
        raise NotImplementedError
