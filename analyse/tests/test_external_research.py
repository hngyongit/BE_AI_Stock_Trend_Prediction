import asyncio

from analyse.config.settings import Settings
from analyse.research.cafef import CafeFResearchAdapter
from analyse.research.google_news import GoogleNewsResearchAdapter
from analyse.research.research_service import ExternalResearchService
from analyse.research.vietstock import VietstockResearchAdapter
from analyse.schemas.research import ResearchItem


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>FPT lợi nhuận tăng, cổ tức tiền mặt</title>
      <link>https://news.google.com/articles/fpt</link>
      <pubDate>Mon, 22 Jun 2026 09:00:00 +0700</pubDate>
      <source url="https://cafef.vn">CafeF</source>
      <description>FPT công bố kết quả kinh doanh tích cực và cổ tức.</description>
    </item>
    <item>
      <title>SSI tin không liên quan</title>
      <link>https://news.google.com/articles/ssi</link>
      <pubDate>Mon, 22 Jun 2026 08:00:00 +0700</pubDate>
      <source url="https://cafef.vn">CafeF</source>
      <description>SSI biến động.</description>
    </item>
  </channel>
</rss>
"""

RSS_WITH_OLD_AND_RETAIL = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>FPT lợi nhuận tăng trong mảng chuyển đổi số</title>
      <link>https://news.google.com/articles/fpt-new</link>
      <pubDate>Mon, 22 Jun 2026 09:00:00 +0700</pubDate>
      <source url="https://cafef.vn">CafeF</source>
      <description>Tập đoàn FPT công bố kết quả kinh doanh tích cực.</description>
    </item>
    <item>
      <title>FPT tin cũ từ năm 2019</title>
      <link>https://news.google.com/articles/fpt-old</link>
      <pubDate>Mon, 01 Jul 2019 09:00:00 +0700</pubDate>
      <source url="https://cafef.vn">CafeF</source>
      <description>FPT cổ phiếu có tin cũ.</description>
    </item>
    <item>
      <title>FPT Retail FRT mở chuỗi mới</title>
      <link>https://news.google.com/articles/frt-retail</link>
      <pubDate>Mon, 22 Jun 2026 08:00:00 +0700</pubDate>
      <source url="https://cafef.vn">CafeF</source>
      <description>FPT Retail và FRT là chủ đề chính.</description>
    </item>
    <item>
      <title>FPT chứng quyền và thông báo chữ ký số</title>
      <link>https://news.google.com/articles/fpt-warrant</link>
      <pubDate>Mon, 22 Jun 2026 07:00:00 +0700</pubDate>
      <source url="https://cafef.vn">CafeF</source>
      <description>Static file chữ ký số không có giá trị phân tích.</description>
    </item>
  </channel>
</rss>
"""


class FakeHttpClient:
    def __init__(self, text=RSS):
        self.text = text
        self.urls = []

    async def get_text(self, url, *, headers=None, params=None):
        self.urls.append(url)
        return self.text


class FailingAdapter:
    source_name = "Failing"

    async def search(self, symbol: str, company: str | None = None):
        raise RuntimeError("boom")


class SuccessfulAdapter:
    source_name = "Successful"

    async def search(self, symbol: str, company: str | None = None):
        return [
            ResearchItem(
                source="CafeF",
                type="mock",
                title=f"{symbol} cổ tức",
                url="https://cafef.vn/fpt.html",
                published_at="2026-06-22T09:00:00+07:00",
                snippet="FPT cổ tức",
                tone="tích cực",
                relevance_score=0.9,
                positive_flags=["cổ tức"],
                catalyst_flags=["cổ tức"],
            )
        ]


def _settings(tmp_path):
    return Settings(
        RESEARCH_CACHE_DIR=str(tmp_path / ".research_cache"),
        RESEARCH_CACHE_TTL_SECONDS=0,
        MAX_RESEARCH_ITEMS=5,
        ENABLE_EXTERNAL_RESEARCH=True,
        ENABLE_GOOGLE_NEWS_RSS=True,
        ENABLE_VIETSTOCK=True,
        ENABLE_CAFEF=True,
    )


def test_google_news_adapter_normalizes_rss_items(tmp_path):
    adapter = GoogleNewsResearchAdapter(_settings(tmp_path), http_client=FakeHttpClient())

    items = asyncio.run(adapter.search("FPT", company="Cong ty Co phan FPT"))

    assert len(items) == 1
    item = items[0]
    assert item.source == "CafeF"
    assert item.title == "FPT lợi nhuận tăng, cổ tức tiền mặt"
    assert item.published_at == "2026-06-22T09:00:00+07:00"
    assert item.tone == "tích cực"
    assert "lợi nhuận tăng" in item.positive_flags
    assert "cổ tức" in item.catalyst_flags


def test_google_news_filters_old_and_fpt_retail_items(tmp_path):
    adapter = GoogleNewsResearchAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient(text=RSS_WITH_OLD_AND_RETAIL),
    )

    items = asyncio.run(adapter.search("FPT", company="CTCP FPT"))

    assert len(items) == 1
    assert items[0].title == "FPT lợi nhuận tăng trong mảng chuyển đổi số"
    assert all("2019" not in (item.title or "") for item in items)
    assert all("FPT Retail" not in (item.title or "") for item in items)
    assert all("chứng quyền" not in (item.title or "").lower() for item in items)


def test_vietstock_and_cafef_adapters_use_google_news_domain_queries(tmp_path):
    fake_http = FakeHttpClient()
    vietstock = VietstockResearchAdapter(_settings(tmp_path), http_client=fake_http)
    cafef = CafeFResearchAdapter(_settings(tmp_path), http_client=fake_http)

    asyncio.run(vietstock.search("FPT"))
    asyncio.run(cafef.search("FPT"))

    joined = " ".join(fake_http.urls)
    assert "site%3Avietstock.vn" in joined
    assert "site%3Acafef.vn" in joined


def test_research_service_failure_does_not_break(monkeypatch, tmp_path):
    monkeypatch.setattr("analyse.research.research_service.VietstockResearchAdapter", lambda settings: FailingAdapter())
    monkeypatch.setattr("analyse.research.research_service.CafeFResearchAdapter", lambda settings: SuccessfulAdapter())
    monkeypatch.setattr("analyse.research.research_service.GoogleNewsResearchAdapter", lambda settings: SuccessfulAdapter())

    context = asyncio.run(ExternalResearchService(_settings(tmp_path)).search("FPT"))

    assert context.status == "partial"
    assert len(context.items) >= 1
    assert context.flag_summary["warnings"]
    assert any(status["status"] == "failed" for status in context.source_statuses)


def test_research_service_builds_adapters_when_env_enabled(tmp_path):
    service = ExternalResearchService(_settings(tmp_path))
    adapters = service._build_adapters()

    names = {adapter.source_name for adapter in adapters}
    assert len(adapters) > 3
    assert {"Vietstock", "CafeF", "Google News RSS"}.issubset(names)
    assert {"Tin nhanh chứng khoán", "VnEconomy", "BNews"}.issubset(names)


def test_research_service_returns_clear_warning_when_no_adapter_enabled(tmp_path):
    settings = Settings(
        RESEARCH_CACHE_DIR=str(tmp_path / ".research_cache"),
        ENABLE_EXTERNAL_RESEARCH=True,
        ENABLE_GOOGLE_NEWS_RSS=False,
        ENABLE_VIETSTOCK=False,
        ENABLE_CAFEF=False,
        RESEARCH_GOOGLE_NEWS_RSS_ENABLED=False,
    )

    context = asyncio.run(ExternalResearchService(settings).search("FPT"))

    assert context.status == "disabled"
    assert "Không có research adapter nào được bật." in context.flag_summary["warnings"]
