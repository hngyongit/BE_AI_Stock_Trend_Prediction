from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings, get_settings
from analyse.research.base import BaseResearchAdapter
from analyse.research.base import CATALYST_KEYWORDS
from analyse.research.base import NEGATIVE_KEYWORDS
from analyse.research.base import POSITIVE_KEYWORDS
from analyse.research.base import infer_tone
from analyse.research.base import keyword_flags
from analyse.research.base import normalize_domain
from analyse.research.base import parse_datetime_for_sort
from analyse.research.base import parse_datetime_to_iso
from analyse.research.base import strip_html
from analyse.schemas.research import ResearchItem


class GoogleNewsResearchAdapter(BaseResearchAdapter):
    source_name = "Google News RSS"

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: HttpClient | None = None,
        *,
        source_name: str | None = None,
        source_type: str = "google_news_rss",
        domain_filter: str | None = None,
        query_suffixes: list[str] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client or HttpClient(timeout_ms=self.settings.research_timeout_ms)
        self.source_name = source_name or self.source_name
        self.source_type = source_type
        self.domain_filter = normalize_domain(domain_filter)
        self.query_suffixes = query_suffixes or []
        self._cache_dir = Path(self.settings.research_cache_dir)

    async def search(self, symbol: str, company: str | None = None) -> list[ResearchItem]:
        if not self.settings.research_google_news_rss_enabled:
            return []

        items: list[ResearchItem] = []
        errors: list[str] = []
        for query in self._build_queries(symbol=symbol, company=company):
            url = self._rss_url(query)
            try:
                xml_text = await self._fetch_with_cache(url)
                items.extend(self._parse_rss(xml_text, symbol=symbol, company=company))
            except Exception as exc:
                errors.append(f"{query}: {type(exc).__name__}")

        if not items and errors:
            raise RuntimeError("; ".join(errors[:3]))
        return self._deduplicate(items)

    def _build_queries(self, *, symbol: str, company: str | None = None) -> list[str]:
        clean_symbol = symbol.strip().upper()
        clean_company = (company or "").strip()
        domain = f" site:{self.domain_filter}" if self.domain_filter else ""
        queries = [
            f"{clean_symbol} cổ phiếu{domain}",
            f"{clean_symbol} kết quả kinh doanh{domain}",
            f"{clean_symbol} cổ tức{domain}",
            f"{clean_symbol} khuyến nghị cổ phiếu{domain}",
        ]
        if clean_symbol == "HPG":
            queries.extend(
                [
                    f"{clean_symbol} thép giá thép{domain}",
                    f"{clean_symbol} HRC quặng sắt{domain}",
                    f"{clean_symbol} đầu tư công xây dựng{domain}",
                ]
            )
        if clean_company:
            queries.insert(1, f"{clean_symbol} {clean_company}{domain}")
        for suffix in self.query_suffixes:
            queries.append(f"{clean_symbol} {suffix}{domain}".strip())

        unique: list[str] = []
        seen: set[str] = set()
        for query in queries:
            compact = " ".join(query.split())
            if compact not in seen:
                unique.append(compact)
                seen.add(compact)
        return unique

    def _rss_url(self, query: str) -> str:
        encoded = quote_plus(query)
        return f"https://news.google.com/rss/search?q={encoded}&hl=vi&gl=VN&ceid=VN:vi"

    async def _fetch_with_cache(self, url: str) -> str:
        cache_path = self._cache_path(url)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        text = await self.http_client.get_text(url, headers={"User-Agent": self.settings.research_user_agent})
        self._write_cache(cache_path, text)
        return text

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> str | None:
        if self.settings.research_cache_ttl_seconds <= 0 or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        cached_at = payload.get("cached_at")
        text = payload.get("text")
        if not isinstance(cached_at, (int, float)) or not isinstance(text, str):
            return None
        if time.time() - cached_at > self.settings.research_cache_ttl_seconds:
            return None
        return text

    def _write_cache(self, path: Path, text: str) -> None:
        if self.settings.research_cache_ttl_seconds <= 0:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"cached_at": time.time(), "text": text}
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return

    def _parse_rss(self, xml_text: str, *, symbol: str, company: str | None = None) -> list[ResearchItem]:
        root = ET.fromstring(xml_text)
        parsed_items: list[ResearchItem] = []
        for item in root.findall(".//item"):
            parsed = self._parse_item(item, symbol=symbol, company=company)
            if parsed is not None:
                parsed_items.append(parsed)
        return parsed_items

    def _parse_item(self, item: ET.Element, *, symbol: str, company: str | None = None) -> ResearchItem | None:
        title = self._text(item, "title")
        link = self._text(item, "link")
        description = strip_html(html.unescape(self._text(item, "description") or ""))
        published_at = parse_datetime_to_iso(self._text(item, "pubDate"))
        source_element = item.find("source")
        rss_source_name = (source_element.text or "").strip() if source_element is not None and source_element.text else None
        rss_source_url = source_element.attrib.get("url") if source_element is not None else None
        source_domain = normalize_domain(rss_source_url or link)

        if self.domain_filter and self.domain_filter not in source_domain:
            return None
        if self._is_too_old(published_at):
            return None
        if self._is_low_value_item(title=title, snippet=description):
            return None
        if not self._is_relevant(title=title, snippet=description, symbol=symbol, company=company):
            return None
        if self._is_irrelevant_fpt_retail(title=title, snippet=description, symbol=symbol, company=company):
            return None

        full_text = " ".join(value for value in (title, description) if value)
        positive_flags = self._dedupe_flags(keyword_flags(full_text, POSITIVE_KEYWORDS))
        negative_flags = self._dedupe_flags(keyword_flags(full_text, NEGATIVE_KEYWORDS))
        catalyst_flags = self._dedupe_flags(keyword_flags(full_text, CATALYST_KEYWORDS))
        relevance_score = self._score_item(
            title=title,
            snippet=description,
            symbol=symbol,
            company=company,
            source_domain=source_domain,
            positive_flags=positive_flags,
            negative_flags=negative_flags,
            catalyst_flags=catalyst_flags,
        )

        return ResearchItem(
            source=rss_source_name or self._source_name_from_domain(source_domain) or self.source_name,
            type=self.source_type,
            title=title,
            url=link,
            published_at=published_at,
            snippet=description,
            tone=infer_tone(positive_flags, negative_flags),
            relevance_score=relevance_score,
            positive_flags=positive_flags,
            negative_flags=negative_flags,
            catalyst_flags=catalyst_flags,
            status="success",
        )

    def _text(self, item: ET.Element, tag: str) -> str | None:
        child = item.find(tag)
        if child is None or child.text is None:
            return None
        normalized = html.unescape(child.text).strip()
        return normalized or None

    def _is_relevant(self, *, title: str | None, snippet: str | None, symbol: str, company: str | None = None) -> bool:
        content = f"{title or ''} {snippet or ''}".lower()
        clean_symbol = symbol.strip().lower()
        if clean_symbol and re_contains_symbol(content, clean_symbol):
            return True
        if company:
            company_words = [word for word in company.lower().split() if len(word) >= 3]
            if company_words and any(word in content for word in company_words[:5]):
                return True
        return False

    def _is_too_old(self, published_at: str | None) -> bool:
        max_days = int(getattr(self.settings, "research_max_article_age_days", 730) or 0)
        if max_days <= 0 or not published_at:
            return False
        parsed = parse_datetime_for_sort(published_at)
        if parsed is None:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days
        return age_days > max_days

    def _is_irrelevant_fpt_retail(self, *, title: str | None, snippet: str | None, symbol: str, company: str | None = None) -> bool:
        if symbol.strip().upper() != "FPT":
            return False
        content = f"{title or ''} {snippet or ''}".lower()
        mentions_retail = "fpt retail" in content or re_contains_symbol(content, "frt")
        if not mentions_retail:
            return False
        parent_markers = (
            "tập đoàn fpt",
            "tap doan fpt",
            "ctcp fpt",
            "công ty cổ phần fpt",
            "cong ty co phan fpt",
            "fpt corporation",
        )
        return not any(marker in content for marker in parent_markers)

    def _is_low_value_item(self, *, title: str | None, snippet: str | None) -> bool:
        content = f"{title or ''} {snippet or ''}".lower()
        low_value_markers = (
            "chứng quyền",
            "covered warrant",
            "warrant",
            "chữ ký số",
            "signature",
            "static file",
            "file đính kèm",
            "thông báo ký số",
            "bản tin chứng quyền",
        )
        return any(marker in content for marker in low_value_markers)

    def _dedupe_flags(self, flags: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for flag in flags:
            clean = flag.strip()
            if clean and clean not in seen:
                result.append(clean)
                seen.add(clean)
        return result

    def _score_item(
        self,
        *,
        title: str | None,
        snippet: str | None,
        symbol: str,
        company: str | None,
        source_domain: str,
        positive_flags: list[str],
        negative_flags: list[str],
        catalyst_flags: list[str],
    ) -> float:
        content = f"{title or ''} {snippet or ''}".lower()
        score = 0.0
        if re_contains_symbol(content, symbol.lower()):
            score += 0.45
        if company:
            company_words = [word for word in company.lower().split() if len(word) >= 3]
            if any(word in content for word in company_words[:5]):
                score += 0.2
        if self.domain_filter and self.domain_filter in source_domain:
            score += 0.2
        score += min(len(positive_flags) + len(negative_flags), 3) * 0.03
        score += min(len(catalyst_flags), 3) * 0.04
        return round(min(score, 1.0), 3)

    def _deduplicate(self, items: list[ResearchItem]) -> list[ResearchItem]:
        result: list[ResearchItem] = []
        seen: set[str] = set()
        for item in sorted(items, key=self._sort_key, reverse=True):
            key = self._dedupe_key(item)
            if key in seen:
                continue
            result.append(item)
            seen.add(key)
        return result

    def _sort_key(self, item: ResearchItem) -> tuple[float, float]:
        published = parse_datetime_for_sort(item.published_at)
        timestamp = published.timestamp() if published else 0.0
        return (timestamp, item.relevance_score or 0.0)

    def _dedupe_key(self, item: ResearchItem) -> str:
        title_key = self._normalize_title_key(item.title)
        if title_key:
            return title_key
        return (item.url or "").strip().lower()

    def _normalize_title_key(self, title: str | None) -> str:
        normalized = re.sub(r"\W+", " ", (title or "").lower()).strip()
        return normalized

    def _source_name_from_domain(self, domain: str) -> str | None:
        if not domain:
            return None
        mapping: dict[str, str] = {
            "vietstock.vn": "Vietstock",
            "cafef.vn": "CafeF",
            "tinnhanhchungkhoan.vn": "Tin nhanh chứng khoán",
            "vneconomy.vn": "VnEconomy",
            "bnews.vn": "BNews",
        }
        for suffix, source_name in mapping.items():
            if domain.endswith(suffix):
                return source_name
        return domain


def re_contains_symbol(content: str, symbol: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(symbol)}(?![a-z0-9])", content))
