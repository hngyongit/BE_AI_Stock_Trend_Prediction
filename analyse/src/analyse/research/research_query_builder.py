from __future__ import annotations

import re

from analyse.config.settings import Settings, get_settings
from analyse.research.base import normalize_domain
from analyse.utils.symbol_utils import normalize_symbol


class ResearchQueryBuilder:
    """Build bounded Vietnamese stock research queries."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_queries(
        self,
        *,
        symbol: str,
        company_name: str | None = None,
        exchange: str | None = None,
        domain_filter: str | None = None,
        domains: list[str] | None = None,
        max_queries: int | None = None,
    ) -> list[str]:
        if domains:
            return self.build_domain_queries(
                symbol=symbol,
                company_name=company_name,
                exchange=exchange,
                domains=domains,
                max_queries=max_queries,
            )
        clean_symbol = normalize_symbol(symbol)
        clean_company = self._clean_company(company_name)
        clean_exchange = str(exchange or "").strip().upper()
        subject = f"{clean_symbol} {clean_company}".strip() if clean_company else f"{clean_symbol} {clean_exchange}".strip()
        domain = normalize_domain(domain_filter)
        suffix = f" site:{domain}" if domain else ""
        base_queries = [
            f"{clean_symbol} cổ phiếu",
            f"{subject} kết quả kinh doanh",
            f"{subject} báo cáo tài chính",
            f"{subject} triển vọng",
            f"{subject} rủi ro",
            f"{subject} Vietstock",
            f"{subject} CafeF",
            f"{subject} Tin nhanh chứng khoán",
            f"{subject} VnEconomy",
            f"{subject} nghị quyết cổ đông",
            f"{subject} cổ tức",
            f"{subject} lãnh đạo",
        ]
        queries = [f"{query}{suffix}" for query in base_queries]
        limit = max_queries or max(4, min(12, int(self.settings.source_backed_research_max_articles or 20)))
        return self._dedupe(queries)[:limit]

    def build_domain_queries(
        self,
        *,
        symbol: str,
        company_name: str | None = None,
        exchange: str | None = None,
        domains: list[str],
        max_queries: int | None = None,
    ) -> list[str]:
        queries: list[str] = []
        per_domain = max(2, (max_queries or 12) // max(1, len(domains)))
        for domain in domains:
            queries.extend(
                self.build_queries(
                    symbol=symbol,
                    company_name=company_name,
                    exchange=exchange,
                    domain_filter=domain,
                    max_queries=per_domain,
                )
            )
        return self._dedupe(queries)[: (max_queries or 24)]

    def _clean_company(self, value: str | None) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:120]

    def _dedupe(self, queries: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for query in queries:
            compact = re.sub(r"\s+", " ", query).strip()
            key = compact.lower()
            if compact and key not in seen:
                result.append(compact)
                seen.add(key)
        return result
