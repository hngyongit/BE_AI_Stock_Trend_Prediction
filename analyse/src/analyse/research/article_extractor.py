from __future__ import annotations

from html.parser import HTMLParser
import html
import re
from typing import Any

from analyse.clients.http_client import HttpClient
from analyse.config.settings import Settings, get_settings
from analyse.research.base import normalize_domain


class _ArticleHTMLParser(HTMLParser):
    DROP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.drop_depth = 0
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.time_values: list[str] = []
        self.body_parts: list[str] = []
        self._current_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in self.DROP_TAGS:
            self.drop_depth += 1
        self._current_tag = lower
        if lower == "time":
            for key, value in attrs:
                if key.lower() == "datetime" and value:
                    self.time_values.append(value.strip())

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in self.DROP_TAGS and self.drop_depth:
            self.drop_depth -= 1
        self._current_tag = None

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        text = re.sub(r"\s+", " ", html.unescape(data or "")).strip()
        if not text:
            return
        if self._current_tag == "title":
            self.title_parts.append(text)
        elif self._current_tag == "h1":
            self.h1_parts.append(text)
        elif self._current_tag in {"p", "li", "td", "h2", "h3", "span", "div"}:
            if not self._looks_like_navigation(text):
                self.body_parts.append(text)

    def _looks_like_navigation(self, text: str) -> bool:
        normalized = text.lower()
        if len(text) <= 2:
            return True
        nav_markers = ("đăng nhập", "menu", "trang chủ", "liên hệ", "cookie", "theo dõi", "facebook", "zalo")
        return any(marker in normalized for marker in nav_markers)


class ArticleExtractor:
    """Fetch and clean article HTML into bounded report evidence text."""

    def __init__(self, settings: Settings | None = None, http_client: HttpClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client or HttpClient(timeout_ms=self.settings.source_backed_research_timeout_ms)

    async def fetch_and_extract(self, url: str) -> dict[str, Any]:
        text = await self.http_client.get_text(url, headers={"User-Agent": self.settings.research_user_agent})
        return self.extract(text, url=url)

    def extract(self, html_text: str, *, url: str | None = None) -> dict[str, Any]:
        parser = _ArticleHTMLParser()
        parser.feed(html_text or "")
        title = self._clean_title(" ".join(parser.h1_parts) or " ".join(parser.title_parts))
        body = self._clean_body(parser.body_parts)
        return {
            "source_domain": normalize_domain(url),
            "url": url,
            "title": title,
            "published_at": parser.time_values[0] if parser.time_values else None,
            "body_text": body[: max(500, min(8000, int(self.settings.source_backed_research_article_body_max_chars or 4000)))],
            "word_count": len(body.split()),
        }

    def _clean_title(self, value: str) -> str | None:
        text = re.sub(r"\s+", " ", value or "").strip(" -|")
        if " - " in text:
            text = text.split(" - ")[0].strip()
        return text or None

    def _clean_body(self, parts: list[str]) -> str:
        clean: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = re.sub(r"\s+", " ", part).strip()
            if len(text) < 20:
                continue
            key = text.lower()
            if key in seen:
                continue
            clean.append(text)
            seen.add(key)
        return "\n".join(clean)
