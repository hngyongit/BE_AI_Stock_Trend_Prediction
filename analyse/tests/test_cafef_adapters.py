import asyncio
import json

from analyse.config.settings import Settings
from analyse.research.cafef_company_adapter import CafeFCompanyAdapter
from analyse.research.cafef_company_adapter import build_cafef_company_url
from analyse.research.cafef_company_adapter import clean_company_name
from analyse.research.cafef_financial_adapter import CAFEF_FINANCIAL_TIMEOUT_WARNING
from analyse.research.cafef_financial_adapter import CafeFFinancialAdapter
from analyse.research.cafef_financial_adapter import build_cafef_financial_url
from analyse.services.stock_data_service import StockDataService


CAFEF_COMPANY_HTML = """
<html><body>
  <h1>VCB - Ngân hàng TMCP Ngoại thương Việt Nam</h1>
  <table>
    <tr><td>Tên công ty</td><td>Ngân hàng TMCP Ngoại thương Việt Nam</td></tr>
    <tr><td>Ngành nghề kinh doanh</td><td>Ngân hàng thương mại, dịch vụ tài chính và các hoạt động hỗ trợ khách hàng doanh nghiệp/cá nhân.</td></tr>
    <tr><td>Nhóm ngành</td><td>Ngân hàng</td></tr>
    <tr><td>Lĩnh vực</td><td>Tài chính</td></tr>
  </table>
  <table>
    <tr><th>Họ tên</th><th>Chức vụ</th></tr>
    <tr><td>Nguyễn Văn A</td><td>Chủ tịch HĐQT</td></tr>
  </table>
  <table>
    <tr><th>Cổ đông</th><th>Số cổ phiếu</th><th>Tỷ lệ</th></tr>
    <tr><td>Nhà nước</td><td>4,000,000,000</td><td>74.8%</td></tr>
  </table>
</body></html>
"""


CAFEF_BANK_FINANCIAL_HTML = """
<html><body>
  <div>Đơn vị: Tỷ đồng</div>
  <table>
    <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
    <tr><td>Thu nhập lãi thuần</td><td>15,200</td><td>14,800</td></tr>
    <tr><td>Lãi/lỗ thuần từ hoạt động dịch vụ</td><td>2,100</td><td>1,900</td></tr>
    <tr><td>Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng</td><td>12,500</td><td>12,000</td></tr>
    <tr><td>Chi phí dự phòng rủi ro tín dụng</td><td>1,800</td><td>1,700</td></tr>
    <tr><td>Tổng lợi nhuận trước thuế</td><td>10,700</td><td>10,300</td></tr>
    <tr><td>Lợi nhuận sau thuế</td><td>8,600</td><td>8,300</td></tr>
    <tr><td>Tổng tài sản</td><td>2,100,000</td><td>2,050,000</td></tr>
    <tr><td>Cho vay khách hàng</td><td>1,300,000</td><td>1,250,000</td></tr>
    <tr><td>Tiền gửi của khách hàng</td><td>1,450,000</td><td>1,410,000</td></tr>
    <tr><td>Vốn chủ sở hữu</td><td>185,000</td><td>180,000</td></tr>
    <tr><td>Chỉ số giá thị trường trên thu nhập (P/E)</td><td>10.2</td><td>10.5</td></tr>
    <tr><td>Chỉ số giá thị trường trên giá trị sổ sách (P/B)</td><td>2.3</td><td>2.4</td></tr>
    <tr><td>ROE</td><td>19.5</td><td>18.9</td></tr>
    <tr><td>ROA</td><td>1.6</td><td>1.5</td></tr>
  </table>
</body></html>
"""


CAFEF_NONBANK_FINANCIAL_HTML = """
<html><body>
  <div>Đơn vị: Tỷ đồng</div>
  <table>
    <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
    <tr><td>Doanh thu thuần về bán hàng và cung cấp dịch vụ</td><td>52,901</td><td>48,000</td></tr>
    <tr><td>Lợi nhuận gộp về bán hàng và cung cấp dịch vụ</td><td>8,365</td><td>7,500</td></tr>
    <tr><td>Tổng lợi nhuận kế toán trước thuế</td><td>10,762</td><td>9,050</td></tr>
    <tr><td>Lợi nhuận sau thuế thu nhập doanh nghiệp</td><td>9,056</td><td>8,100</td></tr>
    <tr><td>Lãi cơ bản trên cổ phiếu (VND)</td><td>2,886.77</td><td>2,500</td></tr>
    <tr><td>Tổng cộng tài sản</td><td>259,328</td><td>250,000</td></tr>
    <tr><td>Nợ phải trả</td><td>119,546</td><td>110,000</td></tr>
    <tr><td>Vốn chủ sở hữu</td><td>139,782</td><td>140,000</td></tr>
    <tr><td>Chỉ số giá thị trường trên thu nhập (P/E)</td><td>9.32</td><td>9.60</td></tr>
    <tr><td>Chỉ số giá thị trường trên giá trị sổ sách (P/B)</td><td>1.48</td><td>1.50</td></tr>
    <tr><td>ROE</td><td>6.64</td><td>6.12</td></tr>
    <tr><td>ROA</td><td>3.48</td><td>3.20</td></tr>
  </table>
</body></html>
"""


CAFEF_GARBAGE_COMPANY_HTML = """
<html><body>
  <title>Ban lãnh đạo & Sở hữu - Công ty cổ phần Tập đoàn Hòa Phát Bảng giá điện tử Danh mục đầu tư Thoát</title>
  <h1>HPG - Ban lãnh đạo & Sở hữu - Công ty cổ phần Tập đoàn Hòa Phát Bảng giá điện tử Danh mục đầu tư</h1>
</body></html>
"""


CAFEF_RATIO_ONLY_HTML = """
<html><body>
  <div>Đơn vị: Tỷ đồng</div>
  <table>
    <tr><th>Chỉ tiêu</th><th>2025</th><th>2024</th></tr>
    <tr><td>Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)</td><td>2,886.77</td><td>2,500</td></tr>
    <tr><td>Giá trị sổ sách của cổ phiếu (BVPS)</td><td>20,000</td><td>18,000</td></tr>
    <tr><td>Chỉ số giá thị trường trên thu nhập (P/E)</td><td>9.32</td><td>10.10</td></tr>
    <tr><td>Chỉ số giá thị trường trên giá trị sổ sách (P/B)</td><td>1.48</td><td>1.50</td></tr>
    <tr><td>Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân (ROEA)</td><td>6.64</td><td>6.12</td></tr>
  </table>
</body></html>
"""


class FakeHttpClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.urls: list[str] = []

    async def get_text(self, url: str, *, headers=None, params=None) -> str:
        self.urls.append(url)
        return self.text


class FakeHttpClientMap:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    async def get_text(self, url: str, *, headers=None, params=None) -> str:
        self.urls.append(url)
        for needle, text in self.responses.items():
            if needle in url:
                return text
        return self.responses.get("default", "<html></html>")


class FakeRenderer:
    def __init__(self, html: str | None = None) -> None:
        self.html = html
        self.called = False

    async def fetch_rendered_html(self, url: str):
        self.called = True
        return self.html, []


def _settings(tmp_path, **overrides):
    values = {
        "RESEARCH_CACHE_DIR": str(tmp_path / ".research_cache"),
        "CAFEF_COMPANY_CACHE_TTL_SECONDS": 0,
        "CAFEF_FINANCIAL_CACHE_TTL_SECONDS": 0,
    }
    values.update(overrides)
    return Settings(**values)


def test_cafef_company_url_builder_lowercases_symbol_exchange_and_formats_template():
    url = build_cafef_company_url("VCB", "HOSE")

    assert url == "https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn"
    assert "{symbol}" not in url
    assert "{exchange}" not in url
    assert "/du-lieu//" not in url
    assert "/VCB-" not in url
    assert "/HOSE/" not in url


def test_cafef_company_url_builder_supports_custom_template_without_duplicate_slashes():
    url = build_cafef_company_url(
        " VCB ",
        " HOSE ",
        "https://cafef.vn//du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn",
    )

    assert url == "https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn"


def test_cafef_company_adapter_builds_lowercase_url_and_parses_profile(tmp_path):
    http = FakeHttpClient(CAFEF_COMPANY_HTML)
    adapter = CafeFCompanyAdapter(_settings(tmp_path), http_client=http, browser_renderer=FakeRenderer())

    result = asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    assert http.urls[0] == "https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn"
    assert any("CompanyIntro.ashx?Symbol=vcb" in url for url in http.urls)
    assert any("ListCeo.ashx?Symbol=vcb" in url for url in http.urls)
    assert any("CoCauSoHuu.ashx?Symbol=vcb" in url for url in http.urls)
    assert result["status"] == "success"
    assert result["company_name"] == "Ngân hàng TMCP Ngoại thương Việt Nam"
    assert result["industry"] == "Ngân hàng"
    assert result["sector"] == "Tài chính"
    assert result["industry_level_1"] == "Tài chính"
    assert result["industry_level_2"] == "Ngân hàng"
    assert result["industry_level_3"] is None
    assert "Ngân hàng thương mại" in result["business_overview"]
    assert result["leadership"][0]["name"] == "Nguyễn Văn A"
    assert result["leadership"][0]["position"] == "Chủ tịch HĐQT"
    assert "ownership_percent" not in result["leadership"][0]
    assert result["ownership"][0]["name"] == "Nhà nước"
    assert result["ownership"][0]["holder"] == "Nhà nước"
    assert result["ownership"][0]["ownership_percent"] == "74.8%"
    assert result["source"] == "CafeF thông tin doanh nghiệp"


def test_cafef_company_browser_fallback_is_called_when_static_html_is_empty(tmp_path):
    renderer = FakeRenderer(CAFEF_COMPANY_HTML)
    adapter = CafeFCompanyAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    assert renderer.called is True
    assert result["status"] == "success"
    assert result["company_name"] == "Ngân hàng TMCP Ngoại thương Việt Nam"


def test_cafef_company_cleaner_rejects_menu_garbage_and_keeps_company_name():
    raw = "Ban lãnh đạo & Sở hữu - Công ty cổ phần Tập đoàn Hòa Phát Bảng giá điện tử Danh mục đầu tư Thoát"

    assert clean_company_name(raw, "HPG") == "Công ty cổ phần Tập đoàn Hòa Phát"


def test_cafef_company_parser_extracts_clean_name_from_metadata_without_fabricating_overview(tmp_path):
    html = """
    <html><head>
      <meta property="og:title" content="VCB: Ban lãnh đạo &amp; Sở hữu - Ngân hàng TMCP Ngoại thương Việt Nam">
      <script type="application/ld+json">{"@type":"Corporation","name":"Ngân hàng TMCP Ngoại thương Việt Nam"}</script>
    </head><body><nav>Bảng giá điện tử Danh mục đầu tư MỚI NHẤT</nav></body></html>
    """
    adapter = CafeFCompanyAdapter(_settings(tmp_path), http_client=FakeHttpClient(html), browser_renderer=FakeRenderer())

    result = adapter.parse_html(html, source_url="https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn", symbol="VCB", exchange="HOSE")

    assert result["company_name"] == "Ngân hàng TMCP Ngoại thương Việt Nam"
    assert result["business_overview"] is None
    assert result["status"] == "partial"
    assert result["source_url"] == "https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn"


def test_cafef_company_parser_extracts_industry_levels(tmp_path):
    html = """
    <html><body><table>
      <tr><td>Lĩnh vực</td><td>Tài chính</td></tr>
      <tr><td>Nhóm ngành</td><td>Tổ chức tín dụng</td></tr>
      <tr><td>Ngành chi tiết</td><td>Ngân hàng</td></tr>
    </table></body></html>
    """
    adapter = CafeFCompanyAdapter(_settings(tmp_path), http_client=FakeHttpClient(html), browser_renderer=FakeRenderer())

    result = adapter.parse_html(html, source_url="https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn", symbol="VCB", exchange="HOSE")

    assert result["industry_level_1"] == "Tài chính"
    assert result["industry_level_2"] == "Tổ chức tín dụng"
    assert result["industry_level_3"] == "Ngân hàng"
    assert result["industry"] == "Ngân hàng"


def test_cafef_company_parser_returns_partial_when_only_garbage_is_found(tmp_path):
    html = "<html><body><nav>Bảng giá điện tử Danh mục đầu tư Thoát MỚI NHẤT DOANH NGHIỆP</nav></body></html>"
    adapter = CafeFCompanyAdapter(_settings(tmp_path), http_client=FakeHttpClient(html), browser_renderer=FakeRenderer())

    result = adapter.parse_html(html, source_url="https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn", symbol="VCB", exchange="HOSE")

    assert result["status"] == "insufficient"
    assert result["company_name"] is None
    assert result["accepted_fields"] == []
    assert "company_name" in result["rejected_fields"]


def test_cafef_company_ajax_extracts_leadership_and_ownership(tmp_path):
    responses = {
        "default": "<html><head><meta property='og:title' content='VCB: Ban lãnh đạo & Sở hữu - Ngân hàng TMCP Ngoại thương Việt Nam'></head></html>",
        "CompanyIntro": '{"Success":true,"Data":{"Name":"Ngân hàng TMCP Ngoại thương Việt Nam","Symbol":"VCB","CenterId":1,"Intro":""}}',
        "ListCeo": '{"Success":true,"Data":[{"GroupName":"Hội đồng quản trị","values":[{"Name":"Ông Nguyễn Văn A","Position":"Chủ tịch HĐQT","LinkCeoDetail":"/du-lieu/ceo/a.chn?cs=vcb"}]}]}',
        "CoCauSoHuu.ashx?Symbol=vcb&Type=SoHuu": '{"Success":true,"Data":[]}',
        "CoCauSoHuu.ashx?Symbol=vcb": '{"Success":true,"Data":{"CoDongSoHuu":[{"Name":"Cổ đông Nhà nước","AssetVolume":"1.000.000","AssetRate":"50,5","UpdatedDate":"01/01/2026"}]}}',
    }
    adapter = CafeFCompanyAdapter(_settings(tmp_path), http_client=FakeHttpClientMap(responses), browser_renderer=FakeRenderer())

    result = asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    assert result["status"] == "success"
    assert result["leadership"][0]["name"] == "Ông Nguyễn Văn A"
    assert result["leadership"][0]["position"] == "Chủ tịch HĐQT"
    assert result["ownership"][0]["holder"] == "Cổ đông Nhà nước"
    assert result["ownership"][0]["ownership_percent"] == "50.5%"


def test_cafef_company_debug_url_artifact_includes_lowercase_url_and_parser_details(tmp_path):
    http = FakeHttpClient(CAFEF_COMPANY_HTML)
    settings = _settings(
        tmp_path,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
    )
    adapter = CafeFCompanyAdapter(settings, http_client=http, browser_renderer=FakeRenderer())

    asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    payload_path = tmp_path / "reports" / "debug" / "VCB_cafef_company_url.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["final_cafef_url"] == "https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn"
    assert payload["symbol_used_in_url"] == "vcb"
    assert payload["exchange_used_in_url"] == "hose"
    assert payload["symbol_is_lowercase"] is True
    assert payload["parser_mode"] == "raw_html"
    assert "company_name" in payload["accepted_fields"]
    assert (tmp_path / "reports" / "debug" / "VCB_cafef_company_request.json").exists()
    assert (tmp_path / "reports" / "debug" / "VCB_cafef_company_tables.json").exists()


def test_cafef_company_parser_extracts_clean_hpg_name_from_garbage_header(tmp_path):
    adapter = CafeFCompanyAdapter(_settings(tmp_path), http_client=FakeHttpClient(CAFEF_GARBAGE_COMPANY_HTML), browser_renderer=FakeRenderer())

    result = adapter.parse_html(CAFEF_GARBAGE_COMPANY_HTML, source_url="https://cafef.vn/du-lieu/hose/hpg-ban-lanh-dao-so-huu.chn", symbol="HPG", exchange="HOSE")

    assert result["company_name"] == "Công ty cổ phần Tập đoàn Hòa Phát"
    assert "Bảng giá điện tử" not in result["company_name"]


def test_cafef_financial_adapter_builds_url_and_extracts_bank_metrics(tmp_path):
    http = FakeHttpClient(CAFEF_BANK_FINANCIAL_HTML)
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=http, browser_renderer=FakeRenderer())

    result = asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    assert http.urls == ["https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"]
    assert result["status"] == "success"
    latest = result["periods"][0]
    assert latest["period"] == "Q1/2026"
    assert latest["net_interest_income"] == 15200
    assert latest["profit_before_tax"] == 10700
    assert latest["profit_after_tax"] == 8600
    assert latest["total_assets"] == 2100000
    assert latest["customer_loans"] == 1300000
    assert latest["customer_deposits"] == 1450000
    assert latest["pe"] == 10.2
    assert latest["pb"] == 2.3
    assert latest["roe"] == 19.5
    assert latest["roa"] == 1.6


def test_cafef_financial_url_builder_lowercases_symbol_exchange():
    url = build_cafef_financial_url(" VCB ", " HOSE ")

    assert url == "https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"
    assert "/HOSE/" not in url
    assert "/VCB-" not in url


def test_cafef_financial_adapter_extracts_nonbank_metrics(tmp_path):
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(CAFEF_NONBANK_FINANCIAL_HTML), browser_renderer=FakeRenderer())

    result = asyncio.run(adapter.fetch("HPG", exchange="HOSE"))

    latest = result["periods"][0]
    assert result["status"] == "success"
    assert latest["revenue"] == 52901
    assert latest["gross_profit"] == 8365
    assert latest["profit_before_tax"] == 10762
    assert latest["profit_after_tax"] == 9056
    assert latest["eps"] == 2886.77
    assert latest["total_assets"] == 259328
    assert latest["total_liabilities"] == 119546
    assert latest["equity"] == 139782
    assert latest["pe"] == 9.32
    assert latest["pb"] == 1.48
    assert latest["roe"] == 6.64
    assert latest["roa"] == 3.48


def test_cafef_financial_parser_extracts_period_headers_metric_rows_and_audit(tmp_path):
    html = """
    <html><body>
      <div>Đơn vị: Tỷ đồng</div>
      <table>
        <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
        <tr><td>Doanh thu thuần</td><td>1,200</td><td>1,100</td></tr>
        <tr><td>Lưu chuyển tiền thuần từ HĐKD</td><td>300</td><td></td></tr>
        <tr><td>Nợ vay ngắn hạn</td><td>250</td><td>240</td></tr>
        <tr><td>Dòng chưa map CafeF</td><td>42</td><td>41</td></tr>
      </table>
    </body></html>
    """
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(html), browser_renderer=FakeRenderer())

    result = adapter.parse_html(html, source_url="https://cafef.vn/du-lieu/hose/hpg-tai-chinh.chn")

    latest = result["periods"][0]
    assert result["status"] == "success"
    assert latest["period"] == "Q1/2026"
    assert latest["revenue"] == 1200
    assert latest["operating_cash_flow"] == 300
    assert latest["short_term_debt"] == 250
    assert result["audit"]["tables_found"] == 1
    assert "Q1/2026" in result["audit"]["raw_period_headers"]
    assert result["audit"]["raw_metric_rows_count"] == 4
    assert any(item["field"] == "operating_cash_flow" for item in result["audit"]["mapped_metrics"])
    assert "Dòng chưa map CafeF" in result["audit"]["unmapped_metrics"]


def test_cafef_financial_parser_handles_blank_cells_safely(tmp_path):
    html = """
    <html><body><table>
      <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
      <tr><td>Doanh thu thuần</td><td>1,200</td><td></td></tr>
      <tr><td>Lợi nhuận sau thuế</td><td>-</td><td>100</td></tr>
      <tr><td>Tổng cộng tài sản</td><td>2,000</td><td>1,900</td></tr>
      <tr><td>Vốn chủ sở hữu</td><td>800</td><td>700</td></tr>
    </table></body></html>
    """
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(html), browser_renderer=FakeRenderer())

    result = adapter.parse_html(html, source_url="https://cafef.vn/du-lieu/hose/hpg-tai-chinh.chn")

    latest = result["periods"][0]
    assert latest["revenue"] == 1200
    assert "profit_after_tax" not in latest
    assert latest["total_assets"] == 2000


def test_cafef_financial_parser_rejects_suspicious_bank_values(tmp_path):
    html = """
    <html><body><table>
      <tr><th>Chỉ tiêu</th><th>Q1/2026</th></tr>
      <tr><td>Thu nhập lãi thuần</td><td>10,000</td></tr>
      <tr><td>Lợi nhuận sau thuế</td><td>8,000</td></tr>
      <tr><td>Tổng tài sản</td><td>10</td></tr>
      <tr><td>Cho vay khách hàng</td><td>1,000,000</td></tr>
      <tr><td>Tiền gửi của khách hàng</td><td>900,000</td></tr>
      <tr><td>ROE</td><td>120</td></tr>
    </table></body></html>
    """
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(html), browser_renderer=FakeRenderer())

    result = adapter.parse_html(html, source_url="https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn")
    latest = result["periods"][0]

    assert "total_assets" not in latest
    assert "roe" not in latest
    assert latest["_suspicious_financial_fields"]


def test_cafef_financial_period_only_data_is_not_loaded(tmp_path):
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient("<div>Q1/2026 Q4/2025</div>"), browser_renderer=FakeRenderer(None))

    result = asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    assert result["status"] in {"partial", "failed", "insufficient"}
    assert result["periods"] == []
    assert StockDataService.valid_financial_periods(result["periods"]) == []


def test_cafef_financial_timeout_returns_insufficient_payload(tmp_path):
    adapter = CafeFFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html></html>"),
        browser_renderer=FakeRenderer(None),
    )
    adapter.browser_renderer.html = None

    async def timeout_fetch(url: str):
        adapter.browser_renderer.called = True
        return None, [CAFEF_FINANCIAL_TIMEOUT_WARNING]

    adapter.browser_renderer.fetch_rendered_html = timeout_fetch

    result = asyncio.run(adapter.fetch("VCB", exchange="HOSE"))

    assert result["status"] == "insufficient"
    assert result["periods"] == []
    assert result["source"] == "CafeF tài chính"
    assert CAFEF_FINANCIAL_TIMEOUT_WARNING in result["warnings"]


def test_cafef_financial_debug_audit_does_not_expose_secrets(tmp_path):
    settings = _settings(
        tmp_path,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        CAFEF_FINANCIAL_URL_TEMPLATE="https://cafef.vn/du-lieu/{exchange}/{symbol}-tai-chinh.chn?api_key=SECRET",
    )
    adapter = CafeFFinancialAdapter(settings, http_client=FakeHttpClient(CAFEF_NONBANK_FINANCIAL_HTML), browser_renderer=FakeRenderer())

    asyncio.run(adapter.fetch("HPG", exchange="HOSE"))

    audit_path = tmp_path / "reports" / "debug" / "HPG_cafef_financial_audit.json"
    assert audit_path.exists()
    text = audit_path.read_text(encoding="utf-8")
    assert "SECRET" not in text


def test_cafef_financial_ratio_only_data_is_partial_not_success(tmp_path):
    adapter = CafeFFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(CAFEF_RATIO_ONLY_HTML), browser_renderer=FakeRenderer())

    result = asyncio.run(adapter.fetch("HPG", exchange="HOSE"))

    assert result["status"] == "partial"
    assert result["financial_ratios_only"] is True
    assert result["periods"][0]["pe"] == 9.32
    assert result["periods"][0]["roe"] == 6.64
    assert any("chỉ số tài chính" in warning for warning in result["warnings"])
