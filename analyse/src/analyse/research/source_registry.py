from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from analyse.config.settings import Settings, get_settings
from analyse.research.base import normalize_domain
from analyse.utils.symbol_utils import normalize_symbol


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    source_type: str
    tier: int
    domain: str | None = None
    url_template: str | None = None
    quality_score: float = 0.75

    def build_url(self, *, symbol: str, exchange: str | None = None) -> str | None:
        if not self.url_template:
            return None
        clean_symbol = normalize_symbol(symbol)
        exchange_value = (exchange or "HOSE").strip()
        return self.url_template.format(
            symbol=clean_symbol,
            symbol_lower=clean_symbol.lower(),
            exchange=exchange_value,
            exchange_lower=exchange_value.lower(),
        )


class SourceRegistry:
    """Central source metadata and source-specific URL builder."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def structured_sources(self) -> list[SourceDefinition]:
        return [
            SourceDefinition(
                name="Dữ liệu giá và thanh khoản",
                source_type="backend",
                tier=1,
                quality_score=1.0,
            ),
            SourceDefinition(
                name="CafeF thông tin doanh nghiệp",
                source_type="company_profile",
                tier=2,
                domain="cafef.vn",
                url_template=self.settings.cafef_company_url_template.replace("{exchange}", "{exchange_lower}").replace("{symbol}", "{symbol_lower}"),
                quality_score=0.9,
            ),
            SourceDefinition(
                name="CafeF tài chính",
                source_type="structured_financial",
                tier=2,
                domain="cafef.vn",
                url_template=self.settings.cafef_financial_url_template.replace("{exchange}", "{exchange_lower}").replace("{symbol}", "{symbol_lower}"),
                quality_score=0.9,
            ),
            SourceDefinition(
                name="Vietstock Finance BCTC",
                source_type="structured_financial",
                tier=2,
                domain="finance.vietstock.vn",
                url_template=self.settings.effective_vietstock_financial_url_template,
                quality_score=0.9,
            ),
            SourceDefinition(
                name="Vietstock peer cùng ngành",
                source_type="peer_data",
                tier=2,
                domain="finance.vietstock.vn",
                url_template=self.settings.vietstock_peer_url_template,
                quality_score=0.88,
            ),
        ]

    def trusted_news_sources(self) -> list[SourceDefinition]:
        result: list[SourceDefinition] = []
        for domain in self._domains(self.settings.research_source_priority):
            result.append(
                SourceDefinition(
                    name=self.display_name_for_domain(domain),
                    source_type="news",
                    tier=3,
                    domain=domain,
                    quality_score=self.quality_for_domain(domain),
                )
            )
        return result

    def official_sources(self) -> list[SourceDefinition]:
        result: list[SourceDefinition] = []
        for domain in self._domains(getattr(self.settings, "research_official_source_priority", "")):
            result.append(
                SourceDefinition(
                    name=self.display_name_for_domain(domain, official=True),
                    source_type="official_disclosure",
                    tier=4,
                    domain=domain,
                    quality_score=1.0,
                )
            )
        return result

    def all_sources(self) -> list[SourceDefinition]:
        seen: set[tuple[str, str | None]] = set()
        result: list[SourceDefinition] = []
        for source in [*self.structured_sources(), *self.trusted_news_sources(), *self.official_sources()]:
            key = (source.name, source.domain)
            if key in seen:
                continue
            result.append(source)
            seen.add(key)
        return result

    def build_source_attempts(self, *, symbol: str, exchange: str | None = None) -> list[dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        for source in self.all_sources():
            attempts.append(
                {
                    "name": source.name,
                    "source_type": source.source_type,
                    "tier": source.tier,
                    "domain": source.domain,
                    "url": source.build_url(symbol=symbol, exchange=exchange),
                    "quality_score": source.quality_score,
                }
            )
        return attempts[: max(1, int(self.settings.source_backed_research_max_sources_per_symbol or 12))]

    def display_name_for_domain(self, domain: str, *, official: bool = False) -> str:
        normalized = normalize_domain(domain)
        mapping = {
            "vietstock.vn": "Vietstock",
            "cafef.vn": "CafeF",
            "tinnhanhchungkhoan.vn": "Tin nhanh chứng khoán",
            "vneconomy.vn": "VnEconomy",
            "bnews.vn": "BNews",
            "vietnambiz.vn": "VietnamBiz",
            "ndh.vn": "NDH",
            "fireant.vn": "FireAnt",
            "stockbiz.vn": "StockBiz",
            "hsx.vn": "HOSE",
            "hnx.vn": "HNX",
            "ssc.gov.vn": "Ủy ban Chứng khoán Nhà nước",
        }
        if normalized in mapping:
            return mapping[normalized] if not official else f"Nguồn công bố chính thức - {mapping[normalized]}"
        return f"Nguồn công bố chính thức - {normalized}" if official else normalized

    def quality_for_domain(self, domain: str) -> float:
        normalized = normalize_domain(domain)
        if normalized in {"vietstock.vn", "cafef.vn"}:
            return 0.85
        if normalized in {"tinnhanhchungkhoan.vn", "vneconomy.vn", "bnews.vn"}:
            return 0.8
        if normalized in {"vietnambiz.vn", "ndh.vn", "fireant.vn", "stockbiz.vn"}:
            return 0.74
        return 0.6

    def _domains(self, value: str | None) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in str(value or "").split(","):
            domain = normalize_domain(item.strip())
            if domain and domain not in seen:
                result.append(domain)
                seen.add(domain)
        return result
