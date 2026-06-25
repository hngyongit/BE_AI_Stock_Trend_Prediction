from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from analyse.research.base import parse_datetime_for_sort
from analyse.research.source_quality import SourceQualityScorer
from analyse.schemas.evidence import ExtractedFact, SourceEvidence
from analyse.schemas.research import ExternalResearchContext, ResearchItem
from analyse.utils.symbol_utils import normalize_symbol


class EvidenceNormalizer:
    """Normalize backend, structured crawler and article data into SourceEvidence."""

    def __init__(self, scorer: SourceQualityScorer | None = None) -> None:
        self.scorer = scorer or SourceQualityScorer()

    def from_summary(
        self,
        *,
        symbol: str,
        exchange: str | None,
        company_name: str | None,
        summary: dict[str, Any],
        research_context: ExternalResearchContext | None,
    ) -> list[SourceEvidence]:
        evidence: list[SourceEvidence] = []
        evidence.extend(self._backend_market_evidence(symbol, exchange, company_name, summary))
        evidence.extend(self._financial_evidence(symbol, exchange, company_name, summary))
        evidence.extend(self._company_profile_evidence(symbol, exchange, company_name, summary))
        evidence.extend(self._peer_evidence(symbol, exchange, company_name, summary))
        evidence.extend(self._news_evidence(symbol, exchange, company_name, research_context))
        return [item for item in evidence if item.usable]

    def dedupe_and_score(
        self,
        evidence: list[SourceEvidence],
        *,
        symbol: str,
        company_name: str | None = None,
        industry: str | None = None,
    ) -> tuple[list[SourceEvidence], list[SourceEvidence]]:
        accepted: list[SourceEvidence] = []
        rejected: list[SourceEvidence] = []
        seen: set[str] = set()
        for item in evidence:
            key = self._dedupe_key(item)
            if key in seen:
                rejected.append(item.model_copy(update={"usable": False, "warnings": [*item.warnings, "duplicate_evidence"]}))
                continue
            seen.add(key)
            reliability = self.scorer.reliability_score(source_name=item.source_name, source_type=item.source_type, url=item.url)
            freshness = self.scorer.freshness_score(item.published_at, source_type=item.source_type)
            relevance = max(
                item.relevance_score,
                self.scorer.relevance_score(
                    title=item.title,
                    summary=item.summary,
                    symbol=symbol,
                    company_name=company_name,
                    industry=industry,
                ),
            )
            updated = item.model_copy(
                update={
                    "reliability_score": round(reliability, 3),
                    "freshness_score": round(freshness, 3),
                    "relevance_score": round(relevance, 3),
                    "inclusion_reason": self.scorer.inclusion_reason(
                        reliability=reliability,
                        relevance=relevance,
                        freshness=freshness,
                    ),
                }
            )
            if self._usable(updated):
                accepted.append(updated)
            else:
                rejected.append(updated.model_copy(update={"usable": False}))
        accepted.sort(key=lambda item: (item.reliability_score, item.relevance_score, item.freshness_score), reverse=True)
        return accepted, rejected

    def _backend_market_evidence(self, symbol: str, exchange: str | None, company_name: str | None, summary: dict[str, Any]) -> list[SourceEvidence]:
        latest = self._dict(summary.get("latest_market"))
        momentum = self._dict(summary.get("momentum"))
        market = self._dict(summary.get("hose_market_context"))
        facts: list[ExtractedFact] = []
        for key, label, unit in (
            ("close_price", "Giá đóng cửa", "VND"),
            ("close", "Giá đóng cửa", "VND"),
            ("volume", "Khối lượng", "cp"),
            ("pe", "P/E", None),
            ("pb", "P/B", None),
            ("roe", "ROE", "%"),
        ):
            if latest.get(key) not in (None, ""):
                facts.append(self._fact(key, label, latest.get(key), source_name="Dữ liệu giá và thanh khoản", unit=unit))
        if momentum.get("chart_period_change_pct") is not None:
            facts.append(self._fact("chart_period_change_pct", "Biến động kỳ chart", momentum.get("chart_period_change_pct"), source_name="Dữ liệu giá và thanh khoản", unit="%"))
        for key, label, unit in (
            ("index_value", "VN-Index", "điểm"),
            ("change_percent", "Biến động VN-Index", "%"),
            ("liquidity", "Thanh khoản thị trường", "cp"),
            ("trading_value_billion", "Giá trị giao dịch thị trường", "tỷ đồng"),
            ("market_health_score", "Điểm sức khỏe thị trường", "điểm"),
        ):
            if market.get(key) not in (None, ""):
                facts.append(self._fact(key, label, market.get(key), source_name="Dữ liệu giá và thanh khoản", unit=unit))
        if not facts:
            return []
        return [
            self._evidence(
                source_name="Dữ liệu giá và thanh khoản",
                source_type="backend",
                symbol=symbol,
                exchange=exchange,
                company_name=company_name,
                title="Backend analysis-data, stock detail và chart",
                summary=f"Ghi nhận {len(facts)} fact về giá, thanh khoản, định giá hoặc bối cảnh thị trường.",
                facts=facts,
                relevance_score=1.0,
            )
        ]

    def _financial_evidence(self, symbol: str, exchange: str | None, company_name: str | None, summary: dict[str, Any]) -> list[SourceEvidence]:
        bctc = self._dict(summary.get("bctc_3q"))
        periods = self._list(bctc.get("periods"))
        if not periods:
            return []
        source_name = self._text(bctc.get("source"), "BCTC đã chuẩn hóa")
        facts: list[ExtractedFact] = [
            self._fact("financial_period_count", "Số kỳ BCTC", len(periods), source_name=source_name, unit="kỳ")
        ]
        latest = periods[0]
        for key, label, unit in (
            ("revenue", "Doanh thu", "tỷ đồng"),
            ("profit_after_tax", "Lợi nhuận sau thuế", "tỷ đồng"),
            ("parent_profit", "Lợi nhuận cổ đông mẹ", "tỷ đồng"),
            ("total_assets", "Tổng tài sản", "tỷ đồng"),
            ("equity", "Vốn chủ sở hữu", "tỷ đồng"),
            ("eps", "EPS", "VND"),
            ("roe", "ROE", "%"),
            ("roa", "ROA", "%"),
            ("net_interest_income", "Thu nhập lãi thuần", "tỷ đồng"),
            ("customer_loans", "Cho vay khách hàng", "tỷ đồng"),
            ("customer_deposits", "Tiền gửi khách hàng", "tỷ đồng"),
        ):
            if latest.get(key) not in (None, ""):
                facts.append(self._fact(key, label, latest.get(key), source_name=source_name, unit=unit, period=latest.get("period")))
        return [
            self._evidence(
                source_name=source_name,
                source_type="structured_financial",
                symbol=symbol,
                exchange=exchange,
                company_name=company_name,
                title="BCTC và chỉ tiêu tài chính đã chuẩn hóa",
                summary=f"Có {len(periods)} kỳ tài chính dùng cho phân tích xu hướng.",
                facts=facts,
                relevance_score=0.95,
            )
        ]

    def _company_profile_evidence(self, symbol: str, exchange: str | None, company_name: str | None, summary: dict[str, Any]) -> list[SourceEvidence]:
        overview = self._dict(summary.get("company_overview"))
        if not overview:
            return []
        facts: list[ExtractedFact] = []
        for key, label in (
            ("company_name", "Tên doanh nghiệp"),
            ("industry", "Ngành"),
            ("industry_level_1", "Nhóm ngành cấp 1"),
            ("industry_level_2", "Nhóm ngành cấp 2"),
            ("industry_level_3", "Ngành chi tiết"),
        ):
            if overview.get(key):
                facts.append(self._fact(key, label, overview.get(key), source_name="CafeF thông tin doanh nghiệp"))
        leadership = self._list(overview.get("leadership"))
        ownership = self._list(overview.get("ownership"))
        if leadership:
            facts.append(self._fact("leadership_count", "Số dòng ban lãnh đạo", len(leadership), source_name="CafeF thông tin doanh nghiệp", unit="dòng"))
        if ownership:
            facts.append(self._fact("ownership_count", "Số dòng sở hữu", len(ownership), source_name="CafeF thông tin doanh nghiệp", unit="dòng"))
        if not facts:
            return []
        return [
            self._evidence(
                source_name=self._text(overview.get("source_display") or overview.get("source"), "CafeF thông tin doanh nghiệp"),
                source_type="company_profile",
                symbol=symbol,
                exchange=exchange,
                company_name=company_name,
                url=overview.get("source_url"),
                title="Hồ sơ doanh nghiệp, lãnh đạo và sở hữu",
                summary="Dùng để xác minh mô hình kinh doanh, ngành, ban lãnh đạo hoặc sở hữu nếu nguồn có dữ liệu.",
                facts=facts,
                relevance_score=0.85,
            )
        ]

    def _peer_evidence(self, symbol: str, exchange: str | None, company_name: str | None, summary: dict[str, Any]) -> list[SourceEvidence]:
        peers = self._list(self._dict(summary.get("industry_peer_context")).get("peers"))
        if not peers:
            return []
        facts = [
            self._fact("peer_count", "Số peer cùng ngành", len(peers), source_name="Vietstock peer cùng ngành", unit="peer")
        ]
        for peer in peers[:5]:
            if peer.get("symbol"):
                facts.append(self._fact("peer_symbol", "Mã peer", peer.get("symbol"), source_name="Vietstock peer cùng ngành"))
        return [
            self._evidence(
                source_name="Vietstock peer cùng ngành",
                source_type="peer_data",
                symbol=symbol,
                exchange=exchange,
                company_name=company_name,
                title="Peer cùng ngành",
                summary=f"Ghi nhận {len(peers)} mã peer để so sánh định giá/tương quan ngành.",
                facts=facts,
                relevance_score=0.8,
            )
        ]

    def _news_evidence(self, symbol: str, exchange: str | None, company_name: str | None, research_context: ExternalResearchContext | None) -> list[SourceEvidence]:
        if not research_context:
            return []
        result: list[SourceEvidence] = []
        for item in research_context.items:
            result.append(self.from_research_item(item, symbol=symbol, exchange=exchange, company_name=company_name))
        return result

    def from_research_item(self, item: ResearchItem, *, symbol: str, exchange: str | None, company_name: str | None) -> SourceEvidence:
        published = parse_datetime_for_sort(item.published_at)
        item_type = str(item.type or "").lower()
        source_type = "official_disclosure" if "official" in item_type else "news"
        facts = [
            self._fact("news_tone", "Sắc thái tin tức", item.tone or "trung tính", source_name=item.source, source_url=item.url, confidence=0.65)
        ]
        flags = [*item.positive_flags, *item.negative_flags, *item.catalyst_flags]
        if flags:
            facts.append(self._fact("news_flags", "Tín hiệu trong tin", ", ".join(flags[:6]), source_name=item.source, source_url=item.url, confidence=0.65))
        return self._evidence(
            source_name=item.source,
            source_type=source_type,
            symbol=symbol,
            exchange=exchange,
            company_name=company_name,
            url=item.url,
            title=item.title,
            published_at=published,
            summary=item.snippet or item.title or "Tin tức/nghiên cứu bên ngoài.",
            facts=facts,
            relevance_score=float(item.relevance_score or 0),
        )

    def _evidence(
        self,
        *,
        source_name: str,
        source_type: str,
        symbol: str,
        exchange: str | None,
        company_name: str | None,
        summary: str,
        facts: list[ExtractedFact],
        title: str | None = None,
        url: str | None = None,
        published_at: datetime | None = None,
        relevance_score: float = 0.0,
    ) -> SourceEvidence:
        return SourceEvidence(
            source_name=source_name,
            source_type=source_type,  # type: ignore[arg-type]
            url=url,
            title=title,
            published_at=published_at,
            crawled_at=datetime.now(timezone.utc),
            symbol=normalize_symbol(symbol),
            exchange=exchange,
            company_name=company_name,
            summary=summary,
            extracted_facts=facts,
            relevance_score=relevance_score,
            usable=bool(facts or summary),
        )

    def _fact(
        self,
        key: str,
        label: str,
        value: Any,
        *,
        source_name: str,
        source_url: str | None = None,
        unit: str | None = None,
        period: str | None = None,
        confidence: float = 0.9,
    ) -> ExtractedFact:
        return ExtractedFact(
            key=key,
            label=label,
            value=value,
            unit=unit,
            period=period,
            confidence=confidence,
            source_name=source_name,
            source_url=source_url,
        )

    def _usable(self, item: SourceEvidence) -> bool:
        if item.source_type in {"backend", "structured_financial", "company_profile", "peer_data"}:
            return item.reliability_score >= 0.75
        return (item.reliability_score * 0.4 + item.relevance_score * 0.4 + item.freshness_score * 0.2) >= 0.45

    def _dedupe_key(self, item: SourceEvidence) -> str:
        return (item.url or f"{item.source_name}:{item.title or item.summary}").strip().lower()

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def _text(self, value: Any, default: str) -> str:
        return str(value).strip() if value not in (None, "") else default
