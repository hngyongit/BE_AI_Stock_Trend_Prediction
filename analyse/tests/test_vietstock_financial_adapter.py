import asyncio

from analyse.config.settings import Settings
from analyse.research.vietstock_financial_adapter import (
    PlaywrightVietstockRenderer,
    VietstockFinancialAdapter,
)
from analyse.services.stock_data_service import StockDataService


VIETSTOCK_TABLE_HTML = """
<html>
  <body>
    <div>Đơn vị: Tỷ đồng</div>
    <table>
      <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
      <tr><td>Doanh thu thuần về bán hàng và cung cấp dịch vụ</td><td>52,901</td><td>48,000</td></tr>
      <tr><td>Giá vốn hàng bán</td><td>44,536</td><td>40,500</td></tr>
      <tr><td>Lợi nhuận gộp về bán hàng và cung cấp dịch vụ</td><td>8,365</td><td>7,500</td></tr>
      <tr><td>Doanh thu hoạt động tài chính</td><td>1,100</td><td>900</td></tr>
      <tr><td>Chi phí tài chính</td><td>800</td><td>700</td></tr>
      <tr><td>Chi phí bán hàng</td><td>1,200</td><td>1,000</td></tr>
      <tr><td>Chi phí quản lý doanh nghiệp</td><td>1,500</td><td>1,300</td></tr>
      <tr><td>Lợi nhuận thuần từ hoạt động kinh doanh</td><td>10,704</td><td>9,000</td></tr>
      <tr><td>Tổng lợi nhuận kế toán trước thuế</td><td>10,762</td><td>9,050</td></tr>
      <tr><td>Lợi nhuận sau thuế thu nhập doanh nghiệp</td><td>9,056</td><td>8,100</td></tr>
      <tr><td>Lợi nhuận sau thuế của Công ty mẹ</td><td>8,994</td><td>8,050</td></tr>
      <tr><td>Lãi cơ bản trên cổ phiếu (VND)</td><td>2,886.77</td><td>2,500</td></tr>
    </table>
    <table>
      <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
      <tr><td>Tài sản ngắn hạn</td><td>104,365</td><td>100,000</td></tr>
      <tr><td>Tiền và các khoản tương đương tiền</td><td>11,455</td><td>10,000</td></tr>
      <tr><td>Các khoản đầu tư tài chính ngắn hạn</td><td>3,000</td><td>2,500</td></tr>
      <tr><td>Các khoản phải thu ngắn hạn</td><td>12,000</td><td>11,000</td></tr>
      <tr><td>Hàng tồn kho</td><td>43,516</td><td>42,000</td></tr>
      <tr><td>Tài sản ngắn hạn khác</td><td>2,200</td><td>2,000</td></tr>
      <tr><td>Tài sản dài hạn</td><td>154,963</td><td>150,000</td></tr>
      <tr><td>Tài sản cố định</td><td>120,000</td><td>118,000</td></tr>
      <tr><td>Bất động sản đầu tư</td><td>1,500</td><td>1,400</td></tr>
      <tr><td>Các khoản đầu tư tài chính dài hạn</td><td>4,500</td><td>4,300</td></tr>
      <tr><td>Tổng cộng tài sản</td><td>259,328</td><td>250,000</td></tr>
      <tr><td>Nợ phải trả</td><td>119,546</td><td>110,000</td></tr>
      <tr><td>Nợ ngắn hạn</td><td>86,370</td><td>80,000</td></tr>
      <tr><td>Nợ dài hạn</td><td>33,176</td><td>30,000</td></tr>
      <tr><td>Vốn chủ sở hữu</td><td>139,782</td><td>140,000</td></tr>
      <tr><td>Vốn đầu tư của chủ sở hữu</td><td>74,000</td><td>74,000</td></tr>
      <tr><td>Thặng dư vốn cổ phần</td><td>5,000</td><td>5,000</td></tr>
      <tr><td>Lợi nhuận sau thuế chưa phân phối</td><td>35,000</td><td>34,000</td></tr>
      <tr><td>Tổng cộng nguồn vốn</td><td>259,328</td><td>250,000</td></tr>
    </table>
    <table>
      <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
      <tr><td>Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)</td><td>5,000</td><td>4,800</td></tr>
      <tr><td>Giá trị sổ sách của cổ phiếu (BVPS)</td><td>23,553</td><td>23,100</td></tr>
      <tr><td>Chỉ số giá thị trường trên thu nhập (P/E)</td><td>9.32</td><td>9.60</td></tr>
      <tr><td>Chỉ số giá thị trường trên giá trị sổ sách (P/B)</td><td>1.48</td><td>1.50</td></tr>
      <tr><td>Tỷ suất lợi nhuận gộp biên</td><td>15.81</td><td>15.63</td></tr>
      <tr><td>Tỷ suất sinh lợi trên doanh thu thuần</td><td>17.12</td><td>16.88</td></tr>
      <tr><td>Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân (ROEA)</td><td>6.64</td><td>6.12</td></tr>
      <tr><td>Tỷ suất lợi nhuận trên tổng tài sản bình quân (ROAA)</td><td>3.48</td><td>3.20</td></tr>
      <tr><td>Tỷ số thanh toán hiện hành (ngắn hạn)</td><td>1.21</td><td>1.25</td></tr>
      <tr><td>Khả năng thanh toán lãi vay</td><td>8.5</td><td>8.0</td></tr>
      <tr><td>Tỷ số Nợ trên Tổng tài sản</td><td>46.1</td><td>44.0</td></tr>
      <tr><td>Tỷ số Nợ vay trên Vốn chủ sở hữu</td><td>0.85</td><td>0.80</td></tr>
    </table>
  </body>
</html>
"""

TEXT_GRID_HTML = """
<html><body>
  <div>Q1/2026 Q4/2025</div>
  <div>Doanh thu thuần về bán hàng và cung cấp dịch vụ 52,901 48,000</div>
  <div>Lợi nhuận sau thuế thu nhập doanh nghiệp 9,056 8,100</div>
  <div>Tổng cộng tài sản 259,328 250,000</div>
</body></html>
"""

FRAGMENTED_TEXT_GRID_HTML = """
<html><body>
  <div>Q1/2026</div><div>Q4/2025</div>
  <div>Doanh thu thuần về bán hàng và cung cấp dịch vụ</div><div>52,901</div><div>48,000</div>
  <div>Lợi nhuận sau thuế thu nhập doanh nghiệp</div><div>9,056</div><div>8,100</div>
  <div>Tổng cộng tài sản</div><div>259,328</div><div>250,000</div>
</body></html>
"""

PERIOD_ONLY_HTML = """
<html><body>
  <div>Q1/2026 Q4/2025 Q3/2025</div>
</body></html>
"""

ANNUAL_HTML = """
<table>
  <tr><th>Chỉ tiêu</th><th>2026</th><th>2025</th></tr>
  <tr><td>Doanh thu thuần về bán hàng và cung cấp dịch vụ</td><td>100,000</td><td>90,000</td></tr>
  <tr><td>Lợi nhuận gộp về bán hàng và cung cấp dịch vụ</td><td>30,000</td><td>25,000</td></tr>
  <tr><td>Lợi nhuận sau thuế thu nhập doanh nghiệp</td><td>12,000</td><td>10,000</td></tr>
</table>
"""

BANK_TABLE_HTML = """
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
    <tr><td>Lợi nhuận sau thuế của cổ đông của ngân hàng mẹ</td><td>8,500</td><td>8,200</td></tr>
    <tr><td>Lãi cơ bản trên cổ phiếu (VND)</td><td>2,500</td><td>2,300</td></tr>
    <tr><td>Tổng tài sản</td><td>2,100,000</td><td>2,050,000</td></tr>
    <tr><td>Tiền mặt, vàng bạc, đá quý</td><td>15,000</td><td>14,000</td></tr>
    <tr><td>Tiền gửi tại NHNN</td><td>80,000</td><td>75,000</td></tr>
    <tr><td>Cho vay khách hàng</td><td>1,300,000</td><td>1,250,000</td></tr>
    <tr><td>Cho vay và cho thuê tài chính khách hàng</td><td>1,305,000</td><td>1,255,000</td></tr>
    <tr><td>Tiền gửi của khách hàng</td><td>1,450,000</td><td>1,410,000</td></tr>
    <tr><td>Các khoản nợ Chính phủ và NHNN</td><td>22,000</td><td>20,000</td></tr>
    <tr><td>Tiền gửi và vay các TCTD khác</td><td>90,000</td><td>85,000</td></tr>
    <tr><td>Vốn chủ sở hữu</td><td>185,000</td><td>180,000</td></tr>
    <tr><td>Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)</td><td>9,100</td><td>8,800</td></tr>
    <tr><td>Giá trị sổ sách của cổ phiếu (BVPS)</td><td>32,000</td><td>31,000</td></tr>
    <tr><td>Chỉ số giá thị trường trên thu nhập (P/E)</td><td>10.2</td><td>10.5</td></tr>
    <tr><td>Chỉ số giá thị trường trên giá trị sổ sách (P/B)</td><td>2.3</td><td>2.4</td></tr>
    <tr><td>NIM</td><td>3.2</td><td>3.1</td></tr>
    <tr><td>Tỷ lệ nợ xấu</td><td>1.1</td><td>1.0</td></tr>
    <tr><td>ROE</td><td>19.5</td><td>18.9</td></tr>
    <tr><td>ROA</td><td>1.6</td><td>1.5</td></tr>
  </table>
</body></html>
"""

BANK_ROAA_VARIANT_HTML = """
<html><body>
  <table>
    <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
    <tr><td>Thu nhập lãi thuần</td><td>20,000</td><td>19,000</td></tr>
    <tr><td>Lợi nhuận sau thuế</td><td>9,000</td><td>8,500</td></tr>
    <tr><td>Tổng cộng tài sản</td><td>2,550,963</td><td>2,450,000</td></tr>
    <tr><td>Cho vay khách hàng</td><td>1,500,000</td><td>1,420,000</td></tr>
    <tr><td>Tiền gửi của khách hàng</td><td>1,600,000</td><td>1,520,000</td></tr>
    <tr><td>Vốn chủ sở hữu</td><td>170,000</td><td>165,000</td></tr>
    <tr><td>Tỷ suất sinh lợi trên tổng tài sản bình quân (ROAA)</td><td>0.38</td><td>0.36</td></tr>
    <tr><td>Tỷ suất lợi nhuận trên vốn chủ sở hữu bình quân (ROEA)</td><td>18.2</td><td>17.8</td></tr>
  </table>
</body></html>
"""

BANK_SUSPICIOUS_TOTAL_ASSETS_HTML = """
<html><body>
  <table>
    <tr><th>Chỉ tiêu</th><th>Q1/2026</th><th>Q4/2025</th></tr>
    <tr><td>Thu nhập lãi thuần</td><td>20,000</td><td>19,000</td></tr>
    <tr><td>Lợi nhuận sau thuế</td><td>9,000</td><td>8,500</td></tr>
    <tr><td>Tổng tài sản</td><td>0.38</td><td>0.36</td></tr>
    <tr><td>Cho vay khách hàng</td><td>1,500,000</td><td>1,420,000</td></tr>
    <tr><td>Tiền gửi của khách hàng</td><td>1,600,000</td><td>1,520,000</td></tr>
    <tr><td>Vốn chủ sở hữu</td><td>2,550,963</td><td>2,450,000</td></tr>
    <tr><td>ROE</td><td>18.2</td><td>17.8</td></tr>
    <tr><td>ROA</td><td>0.38</td><td>0.36</td></tr>
  </table>
</body></html>
"""

JSON_XHR_HTML = """
<script type="application/json" data-vietstock-financial-xhr>
[
  {"period": "Q1/2026", "revenue": 52901, "grossProfit": 8365, "profitAfterTax": 9056, "totalAssets": 259328},
  {"period": "Q4/2025", "revenue": 48000, "grossProfit": 7500, "profitAfterTax": 8100, "totalAssets": 250000}
]
</script>
"""


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeHttpClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.urls = []

    async def get(self, url, *, headers=None, params=None):
        self.urls.append(url)
        return FakeResponse(self.text)


class FakeBrowserRenderer:
    def __init__(self, html: str | None, warnings: list[str] | None = None) -> None:
        self.html = html
        self.warnings = warnings or []
        self.called = False

    async def fetch_rendered_html(self, url: str):
        self.called = True
        return self.html, self.warnings


def _settings(tmp_path, **overrides):
    values = {
        "RESEARCH_CACHE_DIR": str(tmp_path / ".research_cache"),
        "VIETSTOCK_FINANCIAL_CACHE_TTL_SECONDS": 0,
        "VIETSTOCK_FINANCIAL_MAX_PERIODS": 8,
        "ENABLE_VIETSTOCK_FINANCIAL_FALLBACK": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_http_parser_still_normalizes_static_table_html(tmp_path):
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient(VIETSTOCK_TABLE_HTML),
        browser_renderer=FakeBrowserRenderer(None),
    )

    result = asyncio.run(adapter.fetch("HPG"))

    assert result["source"] == "Vietstock Finance"
    assert result["source_url"].endswith("/HPG/tai-chinh.htm?tab=BCTT")
    assert result["unit"] == "Tỷ đồng"
    assert result["status"] == "success"
    assert len(result["periods"]) == 2
    latest = result["periods"][0]
    assert latest["period"] == "Q1/2026"
    assert latest["revenue"] == 52901
    assert latest["cost_of_goods_sold"] == 44536
    assert latest["financial_income"] == 1100
    assert latest["financial_expense"] == 800
    assert latest["selling_expense"] == 1200
    assert latest["general_admin_expense"] == 1500
    assert latest["gross_profit"] == 8365
    assert latest["operating_profit"] == 10704
    assert latest["profit_before_tax"] == 10762
    assert latest["profit_after_tax"] == 9056
    assert latest["parent_profit"] == 8994
    assert latest["eps"] == 2886.77
    assert latest["current_assets"] == 104365
    assert latest["cash"] == 11455
    assert latest["short_term_investments"] == 3000
    assert latest["short_term_receivables"] == 12000
    assert latest["inventory"] == 43516
    assert latest["long_term_assets"] == 154963
    assert latest["fixed_assets"] == 120000
    assert latest["total_assets"] == 259328
    assert latest["total_liabilities"] == 119546
    assert latest["current_liabilities"] == 86370
    assert latest["long_term_liabilities"] == 33176
    assert latest["equity"] == 139782
    assert latest["total_capital"] == 259328
    assert latest["eps_ttm"] == 5000
    assert latest["bvps"] == 23553
    assert latest["pe"] == 9.32
    assert latest["pb"] == 1.48
    assert latest["gross_margin"] == 15.81
    assert latest["net_margin"] == 17.12
    assert latest["roe"] == 6.64
    assert latest["roa"] == 3.48
    assert latest["current_ratio"] == 1.21
    assert latest["interest_coverage"] == 8.5
    assert latest["debt_to_assets"] == 46.1
    assert latest["debt_to_equity"] == 0.85


def test_parser_normalizes_bank_bctc_metrics(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(BANK_TABLE_HTML, source_url="https://finance.vietstock.vn/VCB/tai-chinh.htm?tab=BCTT")

    assert result["status"] == "success"
    latest = result["periods"][0]
    assert latest["period"] == "Q1/2026"
    assert latest["net_interest_income"] == 15200
    assert latest["net_fee_income"] == 2100
    assert latest["pre_provision_operating_profit"] == 12500
    assert latest["credit_provision_expense"] == 1800
    assert latest["profit_before_tax"] == 10700
    assert latest["profit_after_tax"] == 8600
    assert latest["parent_profit"] == 8500
    assert latest["eps"] == 2500
    assert latest["total_assets"] == 2100000
    assert latest["cash_and_gold"] == 15000
    assert latest["deposit_at_state_bank"] == 80000
    assert latest["customer_loans"] == 1305000
    assert latest["customer_deposits"] == 1450000
    assert latest["government_and_state_bank_debt"] == 22000
    assert latest["interbank_liabilities"] == 90000
    assert latest["equity"] == 185000
    assert latest["eps_ttm"] == 9100
    assert latest["bvps"] == 32000
    assert latest["pe"] == 10.2
    assert latest["pb"] == 2.3
    assert latest["nim"] == 3.2
    assert latest["npl_ratio"] == 1.1
    assert latest["roe"] == 19.5
    assert latest["roa"] == 1.6


def test_bank_roaa_variant_maps_to_roa_not_total_assets(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(BANK_ROAA_VARIANT_HTML, source_url="https://finance.vietstock.vn/VCB/tai-chinh.htm?tab=BCTT")

    latest = result["periods"][0]
    assert result["status"] == "success"
    assert latest["total_assets"] == 2550963
    assert latest["equity"] == 170000
    assert latest["roa"] == 0.38
    assert latest["roe"] == 18.2


def test_suspicious_bank_total_assets_and_equity_are_rejected(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(BANK_SUSPICIOUS_TOTAL_ASSETS_HTML, source_url="https://finance.vietstock.vn/VCB/tai-chinh.htm?tab=BCTT")

    latest = result["periods"][0]
    assert latest.get("total_assets") is None
    assert latest.get("equity") is None
    assert latest["roa"] == 0.38
    assert any("Tổng tài sản ngân hàng bị loại" in warning for warning in result["warnings"])


def test_parser_reads_financial_json_payload_from_rendered_html(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(JSON_XHR_HTML, source_url="https://finance.vietstock.vn/HPG/tai-chinh.htm?tab=BCTT")

    assert result["status"] == "success"
    assert result["periods"][0]["period"] == "Q1/2026"
    assert result["periods"][0]["revenue"] == 52901
    assert result["periods"][0]["gross_profit"] == 8365
    assert result["periods"][0]["profit_after_tax"] == 9056
    assert result["periods"][0]["total_assets"] == 259328


def test_browser_fallback_is_called_when_static_html_has_no_tables(tmp_path):
    renderer = FakeBrowserRenderer(VIETSTOCK_TABLE_HTML)
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("HPG"))

    assert renderer.called is True
    assert result["status"] == "success"
    assert result["periods"][0]["period"] == "Q1/2026"
    assert any("HTML tĩnh" in warning for warning in result["warnings"])


def test_playwright_wait_strategy_does_not_rely_on_networkidle(tmp_path):
    renderer = PlaywrightVietstockRenderer(_settings(tmp_path, VIETSTOCK_BCTC_BROWSER_WAIT_UNTIL="networkidle"))

    assert renderer._safe_wait_until("networkidle") == "domcontentloaded"
    assert renderer._safe_wait_until("load") == "load"


def test_browser_fallback_can_parse_rendered_text_grid(tmp_path):
    renderer = FakeBrowserRenderer(TEXT_GRID_HTML)
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("HPG"))

    assert result["status"] == "success"
    assert result["periods"][0]["revenue"] == 52901
    assert result["periods"][0]["profit_after_tax"] == 9056
    assert result["periods"][0]["total_assets"] == 259328


def test_browser_fallback_can_parse_fragmented_rendered_text_grid(tmp_path):
    renderer = FakeBrowserRenderer(FRAGMENTED_TEXT_GRID_HTML)
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("HPG"))

    assert result["status"] == "success"
    assert result["periods"][0]["revenue"] == 52901
    assert result["periods"][0]["profit_after_tax"] == 9056
    assert result["periods"][0]["total_assets"] == 259328


def test_period_only_vietstock_payload_is_partial_not_success(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(PERIOD_ONLY_HTML, source_url="https://finance.vietstock.vn/HPG/tai-chinh.htm?tab=BCTT")

    assert result["status"] == "partial"
    assert result["periods"] == []
    assert any("chưa trích xuất đủ số liệu" in warning.lower() for warning in result["warnings"])


def test_browser_fallback_can_be_disabled(tmp_path):
    renderer = FakeBrowserRenderer(VIETSTOCK_TABLE_HTML)
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path, VIETSTOCK_FINANCIAL_USE_BROWSER_FALLBACK=False),
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("HPG"))

    assert renderer.called is False
    assert result["status"] == "partial"
    assert result["periods"] == []


def test_playwright_renderer_handles_missing_dependency_gracefully(monkeypatch, tmp_path):
    def missing_import(name):
        if name == "playwright.async_api":
            raise ImportError("not installed")
        raise AssertionError(name)

    monkeypatch.setattr("analyse.research.vietstock_financial_adapter.importlib.import_module", missing_import)
    renderer = PlaywrightVietstockRenderer(_settings(tmp_path))

    html, warnings = asyncio.run(renderer.fetch_rendered_html("https://finance.vietstock.vn/HPG/tai-chinh.htm?tab=BCTT"))

    assert html is None
    assert any("Playwright chưa được cài đặt" in warning for warning in warnings)


def test_browser_fallback_handles_timeout_without_crashing(tmp_path):
    renderer = FakeBrowserRenderer(None, ["Playwright rendering failed: TimeoutError: timeout"])
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("HPG"))

    assert result["status"] == "failed"
    assert result["periods"] == []
    assert any("TimeoutError" in warning for warning in result["technical_warnings"])


def test_financial_debug_artifacts_are_written_when_enabled(tmp_path):
    renderer = FakeBrowserRenderer(VIETSTOCK_TABLE_HTML)
    settings = _settings(
        tmp_path,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        VIETSTOCK_DEBUG_SAVE_RENDERED_HTML=True,
        VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=True,
    )
    adapter = VietstockFinancialAdapter(
        settings,
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("HPG"))

    debug_dir = tmp_path / "reports" / "debug"
    assert result["periods"]
    assert (debug_dir / "HPG_vietstock_bctc_rendered.html").exists()
    assert (debug_dir / "HPG_vietstock_bctc_extraction.json").exists()


def test_parser_detects_annual_periods_when_quarters_are_absent(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(ANNUAL_HTML, source_url="https://finance.vietstock.vn/HPG/tai-chinh.htm?tab=BCTT")

    assert result["status"] == "success"
    assert result["periods"][0]["period"] == "2026"
    assert result["periods"][0]["quarter"] is None
    assert result["periods"][0]["revenue"] == 100000


def test_numeric_parser_handles_vietnamese_formats(tmp_path):
    adapter = VietstockFinancialAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    assert adapter._parse_number("52,901") == 52901
    assert adapter._parse_number("1,824.53") == 1824.53
    assert adapter._parse_number("-10.78") == -10.78
    assert adapter._parse_number("(1,234)") == -1234
    assert adapter._parse_number("Chưa có dữ liệu") is None
    assert adapter._parse_number("") is None


def test_merge_financial_fallback_sets_loaded_flags_and_units(tmp_path):
    adapter = VietstockFinancialAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient(VIETSTOCK_TABLE_HTML),
        browser_renderer=FakeBrowserRenderer(None),
    )
    fallback_payload = asyncio.run(adapter.fetch("HPG"))

    merged = StockDataService().merge_financial_fallback(
        {
            "symbol": "HPG",
            "financials": {"periods": []},
            "financial_balance": {},
            "data_quality": {"missing_fields": ["financials.periods"], "warnings": []},
        },
        fallback_payload,
    )

    assert merged["data_quality"]["financials_loaded"] is True
    assert merged["data_quality"]["financial_periods_count"] == 2
    assert merged["data_quality"]["units"]["financial_statement_money_fields"] == "Tỷ đồng"
    assert merged["financial_balance"]["total_assets"] == 259328
    assert "financials.periods" not in merged["data_quality"]["missing_fields"]
