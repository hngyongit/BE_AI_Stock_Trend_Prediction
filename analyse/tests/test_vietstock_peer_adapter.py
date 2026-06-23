import asyncio

from analyse.config.settings import Settings
from analyse.research.vietstock_peer_adapter import PlaywrightVietstockPeerRenderer
from analyse.research.vietstock_peer_adapter import VietstockPeerAdapter
from analyse.services.stock_data_service import StockDataService


def _overview_table(rows: str) -> str:
    return f"""
<html><body>
  <h2>Tổng quan</h2>
  <table>
    <tr>
      <th>STT</th>
      <th>Mã chứng khoán</th>
      <th>Doanh nghiệp</th>
      <th>Sàn</th>
      <th>Giá đóng cửa (VND)</th>
      <th>% Thay đổi 1D (%)</th>
      <th>KL khớp lệnh (Cổ phiếu)</th>
      <th>GT khớp lệnh (Tỷ đồng)</th>
      <th>Xếp hạng cơ bản (Điểm)</th>
      <th>Tín hiệu mua bán</th>
      <th>Vốn hóa (Tỷ đồng)</th>
      <th>EPS 4 quý (VND)</th>
      <th>P/E cơ bản (Lần)</th>
      <th>MACD (Điểm)</th>
      <th>RSI (14) (Điểm)</th>
      <th>Điểm cơ bản</th>
      <th>Ngày GD đầu tiên</th>
    </tr>
    {rows}
  </table>
  <nav>SPOT TIN DOANH GIAO THANH TOP QUY THEO DANH DOANHNGHIEP LOGIN SEARCH MENU</nav>
</body></html>
"""


CMG_SAME_INDUSTRY_HTML = _overview_table(
    """
    <tr><td>1</td><td>CMG</td><td>CTCP Tập đoàn Công nghệ CMC</td><td>HOSE</td><td>42,000</td><td>-0.5</td><td>1,000,000</td><td>42.0</td><td>B</td><td>Trung tính</td><td>15,000</td><td>2,000</td><td>21.0</td><td>-120.5</td><td>45.2</td><td>6.5</td><td>22/01/2010</td></tr>
    <tr><td>2</td><td>FPT</td><td>CTCP FPT</td><td>HOSE</td><td>70,600</td><td>-1.26</td><td>9,260,100</td><td>654.80</td><td>A</td><td>Bán mạnh</td><td>120,267.60</td><td>6,021</td><td>15.91</td><td>-4077.9327</td><td>26.4598</td><td>7.5</td><td>13/12/2006</td></tr>
    <tr><td>3</td><td>ELC</td><td>CTCP Công nghệ - Viễn thông ELCOM</td><td>HOSE</td><td>19,200</td><td>0.8</td><td>500,000</td><td>9.6</td><td>B</td><td>Mua</td><td>2,200</td><td>1,200</td><td>16.0</td><td>10.1</td><td>51.2</td><td>6.0</td><td>18/10/2010</td></tr>
    <tr><td>4</td><td>ITD</td><td>CTCP Công nghệ Tiên Phong</td><td>HOSE</td><td>13,500</td><td>1.1</td><td>220,000</td><td>2.9</td><td>C</td><td>Trung tính</td><td>900</td><td>900</td><td>15.0</td><td>5.5</td><td>49.5</td><td>5.0</td><td>20/12/2010</td></tr>
    <tr><td>5</td><td>HPT</td><td>CTCP Dịch vụ Công nghệ Tin học HPT</td><td>UPCOM</td><td>8,800</td><td>-0.2</td><td>80,000</td><td>0.7</td><td>C</td><td>Cần chờ</td><td>350</td><td>500</td><td>17.6</td><td>-2.5</td><td>42.0</td><td>4.7</td><td>01/08/2017</td></tr>
    <tr><td>6</td><td>SBD</td><td>CTCP Công nghệ Sao Bắc Đẩu</td><td>UPCOM</td><td>12,100</td><td>0.0</td><td>35,000</td><td>0.4</td><td>C</td><td>Trung tính</td><td>400</td><td>600</td><td>20.2</td><td>1.2</td><td>47.1</td><td>4.8</td><td>16/07/2010</td></tr>
    <tr><td>7</td><td>PIA</td><td>CTCP Tin học Viễn thông Petrolimex</td><td>HNX</td><td>25,000</td><td>0.4</td><td>12,000</td><td>0.3</td><td>B</td><td>Trung tính</td><td>500</td><td>1,800</td><td>13.9</td><td>0.2</td><td>55.1</td><td>5.8</td><td>12/09/2012</td></tr>
    <tr><td>8</td><td>CMT</td><td>CTCP Công nghệ mạng và Truyền thông</td><td>HOSE</td><td>9,900</td><td>-0.1</td><td>45,000</td><td>0.5</td><td>C</td><td>Cần chờ</td><td>250</td><td>400</td><td>24.8</td><td>-1.5</td><td>39.0</td><td>4.2</td><td>15/05/2009</td></tr>
    <tr><td>9</td><td>PAI</td><td>CTCP Công nghệ PAI</td><td>UPCOM</td><td>7,700</td><td>0.3</td><td>15,000</td><td>0.1</td><td>C</td><td>Cần chờ</td><td>180</td><td>300</td><td>25.7</td><td>0.6</td><td>44.0</td><td>4.0</td><td>10/10/2018</td></tr>
    """
)


VCB_SAME_INDUSTRY_HTML = _overview_table(
    """
    <tr><td>1</td><td>VCB</td><td>Ngân hàng TMCP Ngoại thương Việt Nam</td><td>HOSE</td><td>65,000</td><td>0.2</td><td>3,000,000</td><td>195.0</td><td>A</td><td>Trung tính</td><td>360,000</td><td>5,500</td><td>11.8</td><td>10.0</td><td>50.2</td><td>8.0</td><td>30/06/2009</td></tr>
    <tr><td>2</td><td>BID</td><td>Ngân hàng TMCP Đầu tư và Phát triển Việt Nam</td><td>HOSE</td><td>42,000</td><td>-0.3</td><td>2,500,000</td><td>105.0</td><td>B</td><td>Trung tính</td><td>250,000</td><td>4,100</td><td>10.2</td><td>-2.1</td><td>48.0</td><td>7.2</td><td>24/01/2014</td></tr>
    <tr><td>3</td><td>CTG</td><td>Ngân hàng TMCP Công Thương Việt Nam</td><td>HOSE</td><td>36,000</td><td>0.4</td><td>4,200,000</td><td>151.2</td><td>B</td><td>Mua</td><td>190,000</td><td>3,600</td><td>10.0</td><td>8.1</td><td>56.1</td><td>7.0</td><td>16/07/2009</td></tr>
    <tr><td>4</td><td>TCB</td><td>Ngân hàng TMCP Kỹ thương Việt Nam</td><td>HOSE</td><td>31,000</td><td>0.1</td><td>5,100,000</td><td>158.1</td><td>A</td><td>Mua</td><td>220,000</td><td>4,000</td><td>7.8</td><td>5.2</td><td>58.0</td><td>7.8</td><td>04/06/2018</td></tr>
    <tr><td>5</td><td>VPB</td><td>Ngân hàng TMCP Việt Nam Thịnh Vượng</td><td>HOSE</td><td>18,000</td><td>-0.5</td><td>6,000,000</td><td>108.0</td><td>B</td><td>Trung tính</td><td>140,000</td><td>2,100</td><td>8.6</td><td>-1.4</td><td>44.0</td><td>6.8</td><td>17/08/2017</td></tr>
    <tr><td>6</td><td>MBB</td><td>Ngân hàng TMCP Quân đội</td><td>HOSE</td><td>25,000</td><td>0.6</td><td>7,000,000</td><td>175.0</td><td>A</td><td>Mua</td><td>150,000</td><td>3,600</td><td>6.9</td><td>12.0</td><td>62.0</td><td>8.1</td><td>01/11/2011</td></tr>
    <tr><td>7</td><td>LPB</td><td>Ngân hàng TMCP Lộc Phát Việt Nam</td><td>HOSE</td><td>22,000</td><td>1.0</td><td>3,500,000</td><td>77.0</td><td>B</td><td>Trung tính</td><td>95,000</td><td>3,000</td><td>7.3</td><td>7.0</td><td>53.0</td><td>6.9</td><td>05/10/2017</td></tr>
    <tr><td>8</td><td>STB</td><td>Ngân hàng TMCP Sài Gòn Thương Tín</td><td>HOSE</td><td>31,000</td><td>-0.2</td><td>8,000,000</td><td>248.0</td><td>B</td><td>Trung tính</td><td>100,000</td><td>4,500</td><td>6.8</td><td>-3.0</td><td>46.0</td><td>7.0</td><td>12/07/2006</td></tr>
    <tr><td>9</td><td>HDB</td><td>Ngân hàng TMCP Phát triển TP.HCM</td><td>HOSE</td><td>28,000</td><td>0.3</td><td>2,700,000</td><td>75.6</td><td>B</td><td>Trung tính</td><td>85,000</td><td>3,500</td><td>8.0</td><td>4.0</td><td>52.0</td><td>6.5</td><td>05/01/2018</td></tr>
    <tr><td>10</td><td>ACB</td><td>Ngân hàng TMCP Á Châu</td><td>HOSE</td><td>26,000</td><td>0.2</td><td>4,500,000</td><td>117.0</td><td>A</td><td>Mua</td><td>120,000</td><td>3,100</td><td>8.4</td><td>9.5</td><td>57.0</td><td>7.7</td><td>31/10/2006</td></tr>
    """
)


QUALITATIVE_LINK_ROWS_HTML = """
<html><body>
  <nav>Tài chính &gt; Tổ chức tín dụng &gt; Ngân hàng</nav>
  <div class="industry-row"><a href="/BID-ngan-hang-tmcp-dau-tu-va-phat-trien-viet-nam.htm">BID - Ngân hàng TMCP Đầu tư và Phát triển Việt Nam</a></div>
  <div class="industry-row"><a href="/CTG-ngan-hang-tmcp-cong-thuong-viet-nam.htm">CTG - Ngân hàng TMCP Công Thương Việt Nam</a></div>
</body></html>
"""


JSON_PEER_HTML = """
<script type="application/json" data-vietstock-peer-xhr>
{
  "data": [
    {"stockCode": "AAA", "companyName": "CTCP Nhựa An Phát Xanh", "marketCode": "HOSE", "closePrice": 9500, "matchedValue": 4.5, "marketCap": 2200, "eps4Q": 1000, "PE": 9.5, "RSI": 55.0},
    {"stockCode": "BMP", "companyName": "CTCP Nhựa Bình Minh", "marketCode": "HOSE", "closePrice": 112000, "matchedValue": 12.4, "marketCap": 9200, "eps4Q": 10000, "PE": 11.2, "RSI": 61.0}
  ]
}
</script>
"""


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeHttpClient:
    def __init__(self, text: str) -> None:
        self.text = text

    async def get(self, url, *, headers=None, params=None):
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
        "VIETSTOCK_PEER_CACHE_TTL_SECONDS": 0,
        "VIETSTOCK_PEER_MAX_ITEMS": 12,
        "ENABLE_VIETSTOCK_PEER_FALLBACK": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_peer_adapter_builds_same_industry_url(tmp_path):
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    assert adapter.settings.vietstock_peer_url_template.format(symbol="CMG") == (
        "https://finance.vietstock.vn/CMG/so-sanh-gia-co-phieu-cung-nganh.htm"
    )


def test_peer_renderer_uses_safe_wait_strategy_and_default_tab(tmp_path):
    settings = _settings(tmp_path, VIETSTOCK_PEER_BROWSER_WAIT_UNTIL="networkidle", VIETSTOCK_PEER_DEFAULT_TAB="Tổng quan")
    renderer = PlaywrightVietstockPeerRenderer(settings)

    assert renderer._safe_wait_until("networkidle") == "domcontentloaded"
    assert renderer.settings.vietstock_peer_default_tab == "Tổng quan"


def test_cmg_overview_table_extracts_requested_peer_tickers_and_columns(tmp_path):
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(CMG_SAME_INDUSTRY_HTML))

    result = adapter.parse_html(CMG_SAME_INDUSTRY_HTML, source_url="https://finance.vietstock.vn/CMG/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="CMG")

    symbols = [peer["symbol"] for peer in result["peers"]]
    assert result["status"] == "success"
    assert "CMG" not in symbols
    for symbol in ["FPT", "ELC", "ITD", "HPT", "SBD", "PIA", "CMT", "PAI"]:
        assert symbol in symbols
    fpt = result["peers"][0]
    assert fpt["symbol"] == "FPT"
    assert fpt["close_price"] == 70600
    assert fpt["change_1d_percent"] == -1.26
    assert fpt["matched_volume"] == 9260100
    assert fpt["matched_value_billion"] == 654.8
    assert fpt["market_cap_billion"] == 120267.6
    assert fpt["eps_4q"] == 6021
    assert fpt["pe_basic"] == 15.91
    assert fpt["macd"] == -4077.9327
    assert fpt["rsi_14"] == 26.4598
    assert fpt["basic_score"] == 7.5
    assert fpt["first_trading_date"] == "13/12/2006"


def test_vcb_overview_table_extracts_bank_peers_and_rejects_noise(tmp_path):
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(VCB_SAME_INDUSTRY_HTML))

    result = adapter.parse_html(VCB_SAME_INDUSTRY_HTML, source_url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="VCB")

    symbols = [peer["symbol"] for peer in result["peers"]]
    assert result["status"] == "success"
    for symbol in ["BID", "CTG", "TCB", "VPB", "MBB", "LPB", "STB", "HDB", "ACB"]:
        assert symbol in symbols
    for invalid in ["SPOT", "TIN", "DOANH", "GIAO", "THANH", "TOP", "QUY", "THEO", "DANH", "DOANHNGHIEP", "LOGIN", "SEARCH", "MENU"]:
        assert invalid not in symbols


def test_peer_browser_fallback_is_called_when_static_html_is_empty(tmp_path):
    renderer = FakeBrowserRenderer(VCB_SAME_INDUSTRY_HTML)
    adapter = VietstockPeerAdapter(
        _settings(tmp_path),
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("VCB"))

    assert renderer.called is True
    assert result["status"] == "success"
    assert [peer["symbol"] for peer in result["peers"]][:3] == ["BID", "CTG", "TCB"]


def test_peer_json_payload_parser_extracts_overview_metrics(tmp_path):
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(""))

    result = adapter.parse_html(JSON_PEER_HTML, source_url="https://finance.vietstock.vn/AAA/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="AAA")

    assert result["status"] == "success"
    assert result["peers"][0]["symbol"] == "BMP"
    assert result["peers"][0]["close_price"] == 112000
    assert result["peers"][0]["matched_value_billion"] == 12.4
    assert result["peers"][0]["market_cap_billion"] == 9200
    assert result["peers"][0]["pe_basic"] == 11.2
    assert result["peers"][0]["rsi_14"] == 61.0


def test_peer_parser_does_not_extract_random_uppercase_page_text(tmp_path):
    html = "<html><body><p>SPOT TIN DOANH GIAO THANH TOP QUY THEO DANH</p></body></html>"
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(html))

    result = adapter.parse_html(html, source_url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="VCB")

    assert result["status"] == "insufficient"
    assert result["peers"] == []


def test_qualitative_stock_links_are_kept_as_reference_peers(tmp_path):
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(QUALITATIVE_LINK_ROWS_HTML))

    result = adapter.parse_html(QUALITATIVE_LINK_ROWS_HTML, source_url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="VCB")

    assert result["status"] == "partial"
    assert [peer["symbol"] for peer in result["peers"]] == ["BID", "CTG"]
    assert result["peers"][0]["quantitative_label"] == "Cần bổ sung: giá, P/E/PB/ROE"
    assert result["industry"]["sector"] == "Tài chính"
    assert result["industry"]["industry_group"] == "Tổ chức tín dụng"
    assert result["industry"]["industry"] == "Ngân hàng"


def test_stock_link_fallback_does_not_dump_full_row_into_company(tmp_path):
    bad_row_html = """
    <html><body>
      <table>
        <tr><td>2</td><td><a href="/BID-ngan-hang.htm">BID</a></td><td>Ngân hàng TMCP Đầu tư và Phát triển Việt Nam</td><td>Bán</td><td>Bán mạnh</td><td>88.6965</td><td>-5321.3235</td></tr>
      </table>
    </body></html>
    """
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(bad_row_html))

    result = adapter.parse_html(bad_row_html, source_url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="VCB")

    assert result["peers"] == []


def test_same_symbol_only_peer_list_is_not_valid(tmp_path):
    html = _overview_table(
        "<tr><td>1</td><td>VCB</td><td>Ngân hàng TMCP Ngoại thương Việt Nam</td><td>HOSE</td><td>65,000</td><td>0.2</td><td>3,000,000</td><td>195.0</td><td>A</td><td>Trung tính</td><td>360,000</td><td>5,500</td><td>11.8</td><td>10.0</td><td>50.2</td><td>8.0</td><td>30/06/2009</td></tr>"
    )
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(html))

    result = adapter.parse_html(html, source_url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="VCB")

    assert result["status"] == "insufficient"
    assert result["peers"] == []
    assert StockDataService.valid_peers(result["peers"], symbol="VCB") == []


def test_peer_parser_splits_symbol_company_combined_cell_from_rendered_table(tmp_path):
    html = """
    <html><body><table>
      <tr><th>STT</th><th>Mã chứng khoán (28)</th><th>Tín hiệu mua bán</th><th>Tín hiệu theo xu hướng</th><th>Mom (10) (Điểm)</th><th>AO (Điểm)</th><th>CCI (20) (Điểm)</th><th>Stoch RSI (3,3,14,14) (Điểm)</th><th>RSI (14) (Điểm)</th><th>MACD (Điểm)</th><th>Vốn hóa (Tỷ đồng)</th></tr>
      <tr><td>1</td><td>VCB Ngân hàng TMCP Ngoại thương Việt Nam</td><td>Trung tính</td><td>Trung tính</td><td>90</td><td>1</td><td>2</td><td>50</td><td>45</td><td>-1</td><td>360,000</td></tr>
      <tr><td>2</td><td>BID Ngân hàng TMCP Đầu tư và Phát triển Việt Nam</td><td>Bán</td><td>Bán mạnh</td><td>88</td><td>-5</td><td>12</td><td>31</td><td>40</td><td>-10</td><td>309,038.77</td></tr>
    </table></body></html>
    """
    adapter = VietstockPeerAdapter(_settings(tmp_path), http_client=FakeHttpClient(html))

    result = adapter.parse_html(html, source_url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm", symbol="VCB")

    assert result["status"] == "success"
    assert result["peers"][0]["symbol"] == "BID"
    assert result["peers"][0]["company"] == "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam"
    assert "88" not in result["peers"][0]["company"]
    assert result["peers"][0]["market_cap_billion"] == 309038.77


def test_peer_debug_artifacts_are_written_when_enabled(tmp_path):
    settings = _settings(
        tmp_path,
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML=True,
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
    )
    renderer = FakeBrowserRenderer(VCB_SAME_INDUSTRY_HTML)
    adapter = VietstockPeerAdapter(
        settings,
        http_client=FakeHttpClient("<html><body>Không có bảng</body></html>"),
        browser_renderer=renderer,
    )

    result = asyncio.run(adapter.fetch("VCB"))

    debug_dir = tmp_path / "reports" / "debug"
    assert result["peers"]
    assert (debug_dir / "VCB_vietstock_peer_rendered.html").exists()
    assert (debug_dir / "VCB_vietstock_peer_request.json").exists()
    assert (debug_dir / "VCB_vietstock_peer_raw.html").exists()
    assert (debug_dir / "VCB_vietstock_peer_tables.json").exists()
    assert (debug_dir / "VCB_vietstock_peer_extraction.json").exists()
    assert (debug_dir / "VCB_vietstock_peer_raw_rows.json").exists()
    assert (debug_dir / "VCB_vietstock_peer_normalized.json").exists()
