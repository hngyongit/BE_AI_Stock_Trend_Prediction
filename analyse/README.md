# Dịch vụ `analyse`

`analyse` là dịch vụ Python/FastAPI tạo báo cáo phân tích cổ phiếu Việt Nam bằng dữ liệu Backend và phần diễn giải LLM có kiểm soát. Endpoint chính:

```http
POST /api/ai-reports/analyse-one
```

Báo cáo này chỉ phục vụ tham khảo/học tập, không phải khuyến nghị đầu tư cá nhân hóa.

Tài liệu vận hành sau refactor nằm ở:

- `../ANALYSE_MAINTENANCE_GUIDE.md`
- `../ANALYSE_DEPLOYMENT_CHECKLIST.md`
- `tests/README.md`

Sau Phase 0-9, các boundary bảo trì chính gồm `ReportService` facade, `ReportStatusService`, `ReportDebugService`, `SourceCollectionCoordinator`, `ReportAssemblyService`, `NumericFactValidationService` và `AiReportHistoryService`. README này giữ vai trò quick start; chi tiết kiến trúc, policy history, numeric guardrail và checklist deploy nằm trong các file trên.

## 1. Cài đặt và chạy service

```powershell
cd analyse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Nếu dùng `uv`:

```powershell
cd analyse
uv sync
uv run python run.py
```

Swagger UI:

```text
http://localhost:5100/api/analyse/docs
```

### CORS cho frontend local

Khi web frontend chạy bằng Vite tại `http://localhost:5173` gọi analyse API tại `http://localhost:5100`, trình duyệt sẽ gửi preflight:

```http
OPTIONS /api/ai-reports/analyse-one
```

Nếu analyse chưa bật CORS middleware, request này có thể trả `405 Method Not Allowed`; Axios thường hiển thị thành `Network Error` dù service vẫn đang chạy. Cấu hình mặc định đã cho phép:

```env
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CORS_ALLOW_CREDENTIALS=true
```

`CORS_ALLOWED_ORIGINS` là danh sách origin phân tách bằng dấu phẩy. Nếu đổi frontend port hoặc domain dev, thêm origin mới vào `.env`, sau đó restart analyse bằng:

```powershell
cd analyse
uv run python run.py
```

Kiểm tra preflight bằng PowerShell:

```powershell
curl.exe -i -X OPTIONS "http://localhost:5100/api/ai-reports/analyse-one" `
  -H "Origin: http://localhost:5173" `
  -H "Access-Control-Request-Method: POST" `
  -H "Access-Control-Request-Headers: authorization,content-type"
```

Kỳ vọng có `HTTP/1.1 200 OK` hoặc `204` và header:

```text
access-control-allow-origin: http://localhost:5173
```

## 2. Cấu hình Backend và LLM

Các biến chính trong `.env`:

```env
BACKEND_API_BASE_URL=http://localhost:5000
# Không đặt user access token trong .env cho analyse-one.
# Frontend gửi token hiện tại qua header Authorization theo dạng <scheme> <token>.
# Deprecated: biến này không được dùng cho user-triggered analyse-one.
BACKEND_API_TOKEN=
BACKEND_API_AUTH_SCHEME=Bearer
BACKEND_API_TIMEOUT_MS=30000
BACKEND_API_VERIFY_SSL=true

BACKEND_USE_ANALYSIS_DATA_ENDPOINT=true
BACKEND_ANALYSIS_DATA_ENDPOINT=/api/stocks/{symbol}/analysis-data
BACKEND_ANALYSIS_DATA_QUARTERS=6
BACKEND_ANALYSIS_DATA_CHART_RANGE=3m
BACKEND_ANALYSIS_DATA_INCLUDE_PEERS=true
BACKEND_ANALYSIS_DATA_INCLUDE_MARKET_CONTEXT=true
# Deprecated for analyse-one: watchlist validation is always required.
BACKEND_WATCHLIST_REQUIRED=false

DEFAULT_LLM_PROVIDER=openai
ALLOW_REQUEST_MODEL_OVERRIDE=true

OPENAI_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini

GEMINI_ENABLED=true
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash
```

Không commit `.env` và không hard-code API key trong source code.

### Contract Backend mới cho `analyse`

Mặc định service gọi endpoint mới:

```http
GET /api/stocks/{symbol}/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Endpoint này trả dữ liệu trong `data` gồm:

- `latestMarket`/`latest_market`
- `priceHistory`/`price_history`
- `financials.periods`
- `financialBalance`/`financial_balance`
- `hoseMarketContext`/`market_overview`
- `industryPeerContext`/`industry_peer_context`
- `marketGeneralContext`/`market_general_context`
- `sameIndustryRecommendation`/`same_industry_recommendation`
- `dataQuality`

Nếu endpoint này lỗi, `analyse` fallback sang endpoint cũ:

```http
GET /api/stocks/{symbol}
GET /api/stocks/{symbol}/chart?range=3m
```

### Token người dùng cho `analyse-one`

`analyse` không đọc token người dùng từ `.env` cho request phân tích do người dùng kích hoạt. Browser `localStorage` chỉ frontend đọc được; vì vậy frontend phải lấy token đăng nhập hiện tại và gửi vào header:

```http
Authorization: <scheme> <access_token>
```

Trong cấu hình mặc định, `<scheme>` là `Bearer`.

`POST /api/ai-reports/analyse-one` dùng token này để gọi Backend `/api/watchlists`, `/api/stocks/{symbol}`, `/api/stocks/{symbol}/analysis-data` và `/api/stocks/{symbol}/chart`. Service không lưu token globally, không cache token và không trả token trong response.

Nếu thiếu header:

```powershell
curl.exe -i -X POST "http://localhost:5100/api/ai-reports/analyse-one" `
  -H "Content-Type: application/json" `
  -d "{\"provider\":\"openai\",\"model\":\"gpt-4.1-mini\",\"symbol\":\"VCB\",\"scopeExchange\":\"HOSE\",\"options\":{\"language\":\"vi\",\"riskProfile\":\"medium\",\"timeHorizon\":\"medium_term\",\"includeExternalResearch\":true,\"renderMarkdown\":false,\"renderHtml\":false,\"capitalVnd\":100000000,\"riskPerTradePct\":1.0,\"maxPositionPct\":12.0}}"
```

Kỳ vọng `401 Unauthorized`.

Nếu có token hợp lệ:

```powershell
curl.exe -i -X POST "http://localhost:5100/api/ai-reports/analyse-one" `
  -H "Content-Type: application/json" `
  -H "Authorization: <scheme> <YOUR_LOGIN_TOKEN>" `
  -d "{\"provider\":\"openai\",\"model\":\"gpt-4.1-mini\",\"symbol\":\"VCB\",\"scopeExchange\":\"HOSE\",\"options\":{\"language\":\"vi\",\"riskProfile\":\"medium\",\"timeHorizon\":\"medium_term\",\"includeExternalResearch\":true,\"renderMarkdown\":false,\"renderHtml\":false,\"capitalVnd\":100000000,\"riskPerTradePct\":1.0,\"maxPositionPct\":12.0}}"
```

Nếu token hợp lệ và mã nằm trong watchlists của người dùng, report được tạo. Nếu token hết hạn/sai, response là `401`. Nếu mã không nằm trong watchlists, response là `403` với thông báo mã không được phép phân tích.

### Kiểm tra cấu hình an toàn

Sau khi copy `.env.example` sang `.env`, dùng endpoint nội bộ sau để kiểm tra cấu hình đã được load đúng hay chưa:

```http
GET http://localhost:5100/api/analyse/config-check
```

Nếu muốn thử kết nối Backend:

```http
GET http://localhost:5100/api/analyse/config-check?checkBackend=true
```

Response chỉ hiển thị token/API key ở dạng `set` hoặc `not_set`, không trả secret thật. Kiểm tra các mục quan trọng:

- `env_file.exists=true`
- `backend.base_url` không có hậu tố `/api`
- `backend.analysis_data_url_example` có dạng `http://localhost:5000/api/stocks/HPG/analysis-data?...`
- `backend.request_auth=required_via_authorization_header` cho biết analyse-one nhận token qua request header
- `backend.env_token_deprecated=set/not_set` chỉ là trạng thái biến cũ, không dùng cho user-triggered analyse-one
- `providers.openai=configured` hoặc `providers.gemini=configured`
- `playwright.package=available` nếu bật fallback trình duyệt

Nếu `BACKEND_API_BASE_URL=http://localhost:5000/api`, service sẽ tự chuẩn hóa thành `http://localhost:5000` để tránh gọi nhầm `/api/api/...`. Nếu thiếu scheme như `localhost:5000`, service trả lỗi cấu hình rõ ràng.

### Cấu hình scoring

```env
ENABLE_SCORING=true
SCORING_MIN_FINANCIAL_PERIODS=3
SCORING_REQUIRE_FINANCIALS_FOR_OVERALL=false
SCORING_ENABLE_MARKET_CONTEXT=true
SCORING_ENABLE_PEER_CONTEXT=true
```

Scoring là chỉ báo định lượng tham khảo, không phải khuyến nghị đầu tư cá nhân hóa.

### Contract trình bày tỷ lệ tin cậy và nguồn dữ liệu

Các trường dùng để vẽ thước đo trong `summary.report_presentation.score_cards` luôn dùng thang `0-100`:

```json
{
  "key": "data_confidence",
  "label": "Tỷ lệ tin cậy dữ liệu",
  "score": 70,
  "meter_percent": 70,
  "display_value": "70%",
  "unit": "%",
  "scale": "0-100"
}
```

Nếu scoring nội bộ tạo confidence dạng tỷ lệ như `0.7`, lớp trình bày sẽ chuyển thành `70` cho `score`/`meter_percent` và `70%` cho `display_value`. `display_value` chỉ dùng để hiển thị chữ; frontend không nên dùng trường này để tính độ rộng thanh tiến trình. Khi không có giá trị thật, score/meter là `null`, không tự ép về `0`.

`data.data_sources` là danh sách nguồn đã được sanitize sẵn cho UI. Tên nguồn và chi tiết nguồn dùng ngôn ngữ tài chính/nghiệp vụ, ví dụ:

- `Backend /api/watchlists` được trình bày thành `Danh sách theo dõi cá nhân`.
- `Backend /api/stocks/:symbol/analysis-data` được trình bày thành `Dữ liệu giá và thanh khoản`.
- `CafeF BCTC` được trình bày thành `CafeF tài chính`.
- `Vietstock Finance BCTC` giữ vai trò nguồn BCTC có thể chuẩn hóa khi fallback thành công.
- `Vietstock peer cùng ngành` được mô tả bằng số mã peer đã ghi nhận, không hiển thị `tables_found`, `page_loaded` hay URL raw.

Các chi tiết kỹ thuật như endpoint `/api/...`, `backend_api`, `exchange=...`, `quarters=...`, `chartRange=...`, `page_loaded`, `tables_found`, `grid_rows_found`, `peer_rows_found`, `normalized_peers`, `periods=...`, `fields=...`, `leadership_rows=...`, `ownership_rows=...` và URL raw không xuất hiện trong `data.data_sources` hoặc mục `Nguồn đã sử dụng` của HTML report.

Khi `renderMarkdown=false` hoặc `renderHtml=false`, service không thêm `Report Markdown file` hoặc `Report HTML file` vào `data_sources`. Đường dẫn file đã tạo, nếu có, nằm trong `markdown_report.output_path` và `html_report.output_path`, không được xem là nguồn tài chính dùng cho phân tích.

Với CafeF tài chính, `periods=0` nghĩa là CafeF đã được kiểm tra nhưng chưa cung cấp đủ kỳ tài chính có thể chuẩn hóa. Nguồn này được trình bày là:

```json
{
  "name": "CafeF tài chính",
  "category": "Báo cáo tài chính",
  "status": "insufficient",
  "status_label": "Chưa đủ dữ liệu"
}
```

Nếu Vietstock Finance BCTC lấy được kỳ tài chính hợp lệ, báo cáo sẽ thể hiện Vietstock Finance là nguồn BCTC có thể dùng trong lần chạy đó.

Chi tiết crawler/debug vẫn được giữ cho developer khi bật:

```env
EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML=true
EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=true
VIETSTOCK_DEBUG_SAVE_RENDERED_HTML=true
VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=true
```

Khi debug bật, xem thêm `reports/debug/{symbol}_user_facing_sources_debug.json` để đối chiếu `raw_source_name`, `raw_detail`, `sanitized_name` và `sanitized_detail`. Các file debug phục vụ kỹ thuật, không phải nội dung hiển thị cho người dùng cuối.

## 3. Bật xuất Markdown và HTML

## Xuất báo cáo Markdown và HTML

Để xuất cả 2 file, request cần:

```json
"options": {
  "renderMarkdown": true,
  "renderHtml": true
}
```

`.env` cần:

```env
REPORT_RENDER_MARKDOWN=true
REPORT_RENDER_HTML=true
```

Sau khi gọi API, kiểm tra:

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\analyse
ls reports
start reports\<report_id>.html
Get-Content reports\<report_id>.md -Encoding UTF8
```

Mặc định service tạo thư mục `reports/` nếu chưa có và ghi hai file:

```text
reports/{report_id}.md
reports/{report_id}.html
```

Cấu hình:

```env
REPORT_OUTPUT_DIR=reports
REPORT_RENDER_MARKDOWN=true
REPORT_RENDER_HTML=true
REPORT_WRITE_MARKDOWN=true
REPORT_WRITE_HTML=true
REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE=true
REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false
```

`REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false` giúp response JSON nhẹ hơn, nhưng file HTML vẫn được ghi ra ổ đĩa.

## Tổng quan doanh nghiệp

Phần `Tổng quan doanh nghiệp` được dựng từ dữ liệu đã xác minh theo thứ tự ưu tiên:

1. Hồ sơ cổ phiếu nội bộ/Backend nếu đã có tên doanh nghiệp, mô tả hoặc ngành sạch.
2. CafeF company/profile page, đặc biệt là trang ban lãnh đạo và sở hữu.
3. Vietstock Finance stock page hoặc breadcrumb ngành.
4. Vietstock peer page heading.
5. External research/news chỉ dùng làm hỗ trợ định tính.
6. Nếu các nguồn đều thiếu, report hiển thị thông báo dữ liệu còn hạn chế thay vì tự suy diễn.

CafeF company fallback dùng mẫu URL:

```text
https://cafef.vn/du-lieu/{exchange_lower}/{symbol_lower}-ban-lanh-dao-so-huu.chn
```

Ví dụ:

```text
https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn
```

Adapter trích xuất các trường có thể xác minh: tên doanh nghiệp, sàn, nhóm ngành, ngành chi tiết, mô tả hoạt động kinh doanh, ban lãnh đạo, sở hữu, nguồn và URL nguồn. Nếu CafeF chỉ cung cấp tên doanh nghiệp thì report chỉ dùng tên đó; không tự tạo mô tả kinh doanh, lãnh đạo, sở hữu hoặc ngành. Nếu CafeF thiếu ngành, service giữ hoặc bổ sung ngành từ Vietstock Finance khi nguồn này có breadcrumb/heading dùng được.

Sau khi có `leadership` và `ownership`, backend đối chiếu tên cá nhân để làm giàu bảng Ban lãnh đạo. Tên được chuẩn hóa bằng cách bỏ kính ngữ như `Ông`, `Bà`, `Mr.`, `Mrs.`, `Ms.`, chuẩn hóa khoảng trắng, lowercase và tạo thêm biến thể không dấu để match an toàn. Ví dụ `Ông Trần Đình Long` có thể match `Trần Đình Long`; `Bà Vũ Thị Hiền` có thể match `Vũ Thị Hiền`. Các cổ đông là tổ chức/quỹ/ngân hàng như Dragon Capital, Deutsche Bank, VinaCapital, Norges Bank hoặc các dòng có marker công ty/quỹ không được dùng để match vào cá nhân lãnh đạo.

Nếu match được, dòng lãnh đạo nhận thêm `shares`, `ownership_percent`, `ownership_source`, `ownership_match`, `ownership_match_confidence` và `ownership_note="Đối chiếu từ bảng cổ đông lớn CafeF"`. Nếu không match được, backend giữ `shares=null`, `ownership_percent=null`, `ownership_match="not_found"` và không tự bịa dữ liệu sở hữu.

Report trình bày phần này theo cấu trúc:

- Hồ sơ doanh nghiệp: doanh nghiệp, sàn, nhóm ngành, mô tả ngắn nếu có và nguồn.
- Ban lãnh đạo: họ tên, chức vụ, số cổ phiếu, tỷ lệ sở hữu và ghi chú nguồn nếu CafeF trích xuất được.
- Sở hữu / cổ đông lớn: cổ đông/tổ chức/cá nhân, số cổ phiếu, tỷ lệ sở hữu và nguồn nếu có.
- Nhóm ngành tham chiếu: nhóm ngành, ngành chi tiết và nguồn, dùng để hỗ trợ peer comparison.

Nếu không trích xuất được ban lãnh đạo hoặc sở hữu từ nguồn công khai trong lần chạy hiện tại, report hiển thị empty state rõ ràng và không tự tạo hàng giả.

Parser không dùng `<title>` một cách mù quáng và sẽ loại các chuỗi dính menu/header như `Bảng giá điện tử`, `Danh mục đầu tư`, `MỚI NHẤT`, `Đọc nhanh`, `CHỨNG KHOÁN`, `DOANH NGHIỆP`. Nếu tên CafeF không sạch, service giữ tên sạch có sẵn từ Backend/Vietstock/request context.

## CafeF thông tin doanh nghiệp

Nguồn `CafeF thông tin doanh nghiệp` dùng trang ban lãnh đạo/sở hữu để lấy hồ sơ doanh nghiệp khi dữ liệu nội bộ còn thiếu. URL được build theo mẫu:

```text
https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn
```

Trong code, `{exchange}` luôn được chuẩn hóa về chữ thường và `{symbol}` luôn được chuẩn hóa về chữ thường. Ví dụ request `symbol=VCB`, `scopeExchange=HOSE` sẽ tạo:

```text
https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn
```

Cấu hình:

```env
ENABLE_CAFEF_COMPANY_FALLBACK=true
CAFEF_COMPANY_URL_TEMPLATE=https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn
CAFEF_COMPANY_TIMEOUT_MS=30000
CAFEF_COMPANY_USE_BROWSER_FALLBACK=true
```

Không nhập thủ công mã uppercase vào URL template. Nếu HTML tĩnh của CafeF chưa đủ nội dung, service thử render bằng Playwright. Nếu CafeF chỉ xác minh được tên doanh nghiệp hoặc chỉ một phần ngành, report ghi nhận một phần và giữ dữ liệu sạch từ Backend/Vietstock cho các trường còn thiếu. Khi CafeF không có dữ liệu hữu ích, report không tự suy diễn mô tả doanh nghiệp/ngành.

Khi bật debug:

```env
EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML=true
EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=true
```

Kiểm tra các file:

```text
reports/debug/{symbol}_cafef_company_url.json
reports/debug/{symbol}_cafef_company_rendered.html
reports/debug/{symbol}_cafef_company_extraction.json
reports/debug/{symbol}_leadership_ownership_merge.json
reports/debug/{symbol}_company_overview_normalized.json
```

Nếu CafeF không có dữ liệu, xem `accepted_fields`, `rejected_fields`, `rejection_reasons`, URL cuối cùng và trạng thái raw/render trong các file debug.

## Biểu đồ HTML report

HTML report ưu tiên dùng ECharts để dựng biểu đồ tài chính tương tác, có trục, tooltip, legend, resize responsive và định dạng số gọn. Mặc định service không dùng CDN, để file HTML có thể mở offline bằng `file:///...`.

Cấu hình:

```env
REPORT_CHART_ENGINE=echarts
REPORT_CHART_ASSET_MODE=local
REPORT_CHART_ASSET_DIR=reports/assets
REPORT_ECHARTS_LOCAL_FILE=echarts.min.js
REPORT_CHART_FALLBACK=inline_svg
REPORT_CHART_ALLOW_CDN=false
REPORT_ECHARTS_CDN_URL=
```

Đặt bundle ECharts local tại:

```text
analyse/src/analyse/assets/echarts.min.js
```

Khi export HTML, service sẽ copy file này sang:

```text
analyse/reports/assets/echarts.min.js
```

HTML report sẽ nhúng bằng đường dẫn tương đối:

```html
<script src="assets/echarts.min.js"></script>
```

Nếu chưa có asset local, report không crash và tự dùng fallback `inline_svg`. Khi muốn tắt ECharts để dùng biểu đồ đơn giản:

```env
REPORT_CHART_ENGINE=inline_svg
```

Chế độ CDN chỉ nên dùng khi phát triển nội bộ và phải bật rõ ràng:

```env
REPORT_CHART_ALLOW_CDN=true
REPORT_CHART_ASSET_MODE=cdn
REPORT_ECHARTS_CDN_URL=<url nội bộ hoặc CDN được phép>
```

Series biểu đồ tài chính được chọn từ dữ liệu hợp lệ đang có. Doanh nghiệp thường ưu tiên doanh thu, lợi nhuận gộp, LNTT, LNST, tổng tài sản, vốn chủ, ROE, P/E, P/B. Ngân hàng ưu tiên thu nhập lãi thuần, LNTT, LNST, cho vay khách hàng, tiền gửi khách hàng, tổng tài sản, vốn chủ, ROE, P/E, P/B. Nếu chỉ có một kỳ, report hiển thị thẻ chỉ tiêu thay vì vẽ xu hướng. Các giá trị nghi ngờ, ví dụ tổng tài sản ngân hàng bị scale sai quá nhỏ, sẽ không được đưa vào chart.

Nếu biểu đồ hiển thị `Đang chuẩn bị biểu đồ...` quá lâu, kiểm tra:

1. `reports/assets/echarts.min.js` có tồn tại không.
2. HTML có load đúng `assets/echarts.min.js` không.
3. Console của trình duyệt có lỗi JSON parse không.
4. `REPORT_CHART_ENGINE` có đúng không.
5. `REPORT_CHART_FALLBACK` có bật `inline_svg` không.

## Thước đo sức khỏe thị trường

Gauge cũ cho phần `Bối cảnh VNINDEX/HoSE` đã được thay bằng thước đo sức khỏe thị trường dạng segmented bar. Mặc định:

```env
REPORT_MARKET_CHART_TYPE=segmented_bar
```

`segmented_bar` được ưu tiên vì đơn giản, dễ đọc, hoạt động offline khi mở file bằng `file:///` và không phụ thuộc ECharts. Ý nghĩa điểm thống nhất:

```text
0 = thận trọng hơn
100 = tích cực hơn
```

Ngưỡng hiển thị:

- `0-39`: Thận trọng
- `40-59`: Trung tính
- `60-79`: Tích cực
- `80-100`: Rất tích cực

Nếu nguồn dữ liệu đang dùng điểm rủi ro với chiều ngược lại, code sẽ chuẩn hóa về điểm sức khỏe thị trường trước khi hiển thị. Các giá trị hỗ trợ:

```env
REPORT_MARKET_CHART_TYPE=segmented_bar
REPORT_MARKET_CHART_TYPE=echarts_bar
REPORT_MARKET_CHART_TYPE=none
```

Kiểm tra file đã tạo:

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\analyse
ls reports
start reports\FPT_HOSE_20260622_105312.html
```

Nếu không thấy file, kiểm tra `warnings` và `data_sources` trong response để biết lỗi ghi Markdown/HTML.

## 4. Bật external research/news

External research dùng nguồn công khai, ưu tiên Backend/structured crawlers trước, sau đó mới dùng Google News RSS và article extraction làm bằng chứng ngữ cảnh. Vietstock và CafeF được hỗ trợ bằng structured crawler riêng cho BCTC/company/peer, đồng thời có truy vấn Google News RSS lọc domain `site:vietstock.vn` và `site:cafef.vn`. Service không bypass paywall, login wall hoặc cơ chế anti-bot.

Pipeline enrichment mới:

1. Dựng source registry theo tier: Backend, Vietstock/CafeF structured, nguồn tin tài chính Việt Nam, nguồn công bố chính thức.
2. Tạo query tiếng Việt theo symbol/company/industry và domain.
3. Crawl/search các nguồn đã cấu hình, trích xuất bài viết sạch, loại script/nav/footer.
4. Chuẩn hóa thành `SourceEvidence` và `ExtractedFact`.
5. Deduplicate theo URL/title, chấm điểm reliability/relevance/freshness.
6. Dùng evidence để tạo executive forecast, scenario xác suất, trigger, invalidation, action monitoring plan và checklist.
7. Numeric facts chỉ dùng khi có nguồn; forecast/scenario là model inference có nhãn rõ.

Cấu hình:

```env
ENABLE_EXTERNAL_RESEARCH=true
ENABLE_VIETSTOCK=true
ENABLE_CAFEF=true
ENABLE_GOOGLE_NEWS_RSS=true
RESEARCH_CACHE_DIR=.research_cache
RESEARCH_CACHE_TTL_SECONDS=21600
RESEARCH_TIMEOUT_MS=20000
MAX_RESEARCH_ITEMS=10
RESEARCH_USER_AGENT=Mozilla/5.0 analyse-service/1.0
RESEARCH_GOOGLE_NEWS_RSS_ENABLED=true
RESEARCH_MAX_ARTICLE_AGE_DAYS=730
RESEARCH_SOURCE_PRIORITY=vietstock.vn,cafef.vn,tinnhanhchungkhoan.vn,vneconomy.vn,bnews.vn,vietnambiz.vn,ndh.vn,fireant.vn,stockbiz.vn
RESEARCH_OFFICIAL_SOURCE_PRIORITY=hsx.vn,hnx.vn,ssc.gov.vn

ENABLE_SOURCE_BACKED_RESEARCH=true
ENABLE_DEEP_RESEARCH_CRAWL=true
SOURCE_BACKED_RESEARCH_TIMEOUT_MS=45000
SOURCE_BACKED_RESEARCH_MAX_ARTICLES=20
SOURCE_BACKED_RESEARCH_MAX_SOURCES_PER_SYMBOL=12
SOURCE_BACKED_RESEARCH_MAX_CRAWL_DEPTH=1
SOURCE_BACKED_RESEARCH_CACHE_TTL_SECONDS=21600
SOURCE_BACKED_RESEARCH_REQUIRE_SOURCE_FOR_NUMERIC_FACTS=true
SOURCE_BACKED_RESEARCH_ARTICLE_BODY_MAX_CHARS=4000

GOOGLE_NEWS_RSS_MAX_ITEMS=15
GOOGLE_NEWS_RSS_LANGUAGE=vi
GOOGLE_NEWS_RSS_COUNTRY=VN

ENABLE_FORECAST_SCENARIOS=true
FORECAST_TIME_HORIZONS=short_term,base_term,medium_term
FORECAST_SCENARIO_COUNT=3
FORECAST_REQUIRE_TRIGGER_AND_INVALIDATION=true
FORECAST_ALLOW_PROBABILISTIC_LANGUAGE=true
FORECAST_DEFAULT_PROBABILITY_METHOD=score_weighted
```

`SOURCE_BACKED_RESEARCH_REQUIRE_SOURCE_FOR_NUMERIC_FACTS=true` nghĩa là service không lấy số tài chính từ bài báo hoặc website ngẫu nhiên. Bài viết/tin tức chỉ tạo bằng chứng định tính như catalyst, rủi ro, sắc thái tin và ngữ cảnh doanh nghiệp/ngành.

Fallback dữ liệu BCTC từ Vietstock Finance khi dữ liệu nội bộ chưa đủ. Tên hiển thị trong report luôn là `Vietstock Finance BCTC`; riêng tham số URL `tab=BCTT` là yêu cầu kỹ thuật của Vietstock và chỉ nên xem là chi tiết cấu hình nội bộ:

```env
ENABLE_VIETSTOCK_BCTC_FALLBACK=true
VIETSTOCK_BCTC_URL_TEMPLATE=https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT
VIETSTOCK_BCTC_TIMEOUT_MS=60000
VIETSTOCK_BCTC_CACHE_TTL_SECONDS=21600
VIETSTOCK_BCTC_MAX_PERIODS=8
VIETSTOCK_BCTC_UNIT=Tỷ đồng
VIETSTOCK_BCTC_USE_BROWSER_FALLBACK=true
VIETSTOCK_BCTC_BROWSER_HEADLESS=true
VIETSTOCK_BCTC_BROWSER_WAIT_UNTIL=domcontentloaded
VIETSTOCK_BCTC_BROWSER_WAIT_SELECTOR=
VIETSTOCK_BCTC_BROWSER_EXTRA_WAIT_MS=5000
VIETSTOCK_BCTC_BROWSER_VIEWPORT_WIDTH=1600
VIETSTOCK_BCTC_BROWSER_VIEWPORT_HEIGHT=1100

# Biến cũ vẫn được hỗ trợ tạm thời để không làm gãy deploy hiện tại.
ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=true
VIETSTOCK_FINANCIAL_URL_TEMPLATE=https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT
VIETSTOCK_FINANCIAL_TIMEOUT_MS=60000
VIETSTOCK_FINANCIAL_CACHE_TTL_SECONDS=21600
VIETSTOCK_FINANCIAL_MAX_PERIODS=8
VIETSTOCK_FINANCIAL_UNIT=Tỷ đồng
VIETSTOCK_FINANCIAL_USE_BROWSER_FALLBACK=true
VIETSTOCK_FINANCIAL_BROWSER_HEADLESS=true
VIETSTOCK_FINANCIAL_BROWSER_WAIT_UNTIL=domcontentloaded
VIETSTOCK_FINANCIAL_BROWSER_WAIT_SELECTOR=
VIETSTOCK_FINANCIAL_BROWSER_EXTRA_WAIT_MS=5000
VIETSTOCK_FINANCIAL_BROWSER_VIEWPORT_WIDTH=1600
VIETSTOCK_FINANCIAL_BROWSER_VIEWPORT_HEIGHT=1100
```

Service ưu tiên dữ liệu BCTC từ Backend `analysis-data`. Chỉ khi chưa có kỳ tài chính hợp lệ, service mới thử tải trang Vietstock Finance công khai bằng HTTP. Một kỳ tài chính chỉ được xem là hợp lệ khi có ít nhất 3 chỉ tiêu định lượng. Với doanh nghiệp thường, các chỉ tiêu gồm doanh thu, lợi nhuận, EPS, tài sản, nợ phải trả, vốn chủ, P/E, P/B, ROE hoặc ROA. Với ngân hàng, parser hỗ trợ thêm thu nhập lãi thuần, thu nhập dịch vụ thuần, lợi nhuận trước dự phòng, chi phí dự phòng, cho vay khách hàng, tiền gửi khách hàng, NIM, nợ xấu, CASA, ROE, ROA, P/E, P/B.

Nếu nội dung tĩnh chưa có bảng tài chính, service dùng Playwright/Chromium để mở trang như trình duyệt thật, chờ nội dung BCTC xuất hiện, lấy DOM đã render và các phản hồi JSON/XHR có liên quan nếu có, sau đó parse lại số liệu. Vietstock có thể giữ kết nối nền nên `networkidle` không ổn định; cấu hình khuyến nghị là `domcontentloaded` hoặc `load`, sau đó chờ selector tài chính như `Thu nhập lãi thuần`, `Doanh thu thuần`, `Lợi nhuận sau thuế`, `Tổng cộng tài sản`, `Cho vay khách hàng`, `Tiền gửi của khách hàng`. Kết quả được cache theo `VIETSTOCK_BCTC_CACHE_TTL_SECONDS` hoặc biến legacy tương ứng để tránh gọi Vietstock lặp lại.

Shared Playwright defaults:

```env
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=90000
PLAYWRIGHT_EXTRA_WAIT_MS=5000
PLAYWRIGHT_WAIT_UNTIL=domcontentloaded
PLAYWRIGHT_RETRY_COUNT=2
PLAYWRIGHT_RETRY_BACKOFF_MS=1500
```

Playwright là dependency runtime tùy chọn nhưng nên được cài nếu bật `VIETSTOCK_FINANCIAL_USE_BROWSER_FALLBACK=true`:

```bash
cd analyse
uv add playwright
uv run playwright install chromium
```

Nếu không dùng `uv`:

```bash
cd analyse
pip install playwright
python -m playwright install chromium
```

Khi deploy Docker/Linux, cần bảo đảm image có browser binary và các thư viện hệ thống mà Chromium cần. Nếu Playwright hoặc Chromium chưa sẵn sàng, report không crash; phần chính chỉ nói dữ liệu tài chính công khai chưa trích xuất được trong lần chạy này, còn chi tiết như timeout/missing browser nằm ở log hoặc JSON kỹ thuật.

Trên Windows/Python 3.13, Playwright cần event loop có hỗ trợ subprocess để launch Chromium. Service tự gọi helper `ensure_windows_proactor_event_loop_policy()` trong `run.py` và trong fallback Vietstock. Nếu FastAPI đã có event loop đang chạy, phần render trình duyệt được cách ly trong thread riêng với event loop mới để tránh lỗi `NotImplementedError`. Nếu vẫn lỗi do môi trường thiếu Chromium hoặc bị chặn, report không crash.

### Playwright `TargetClosedError` và cleanup an toàn

CafeF/Vietstock fallback có thể dùng Playwright cho các trang render động: CafeF thông tin doanh nghiệp, CafeF BCTC, Vietstock Finance BCTC và Vietstock peer cùng ngành. Lỗi:

```text
Future exception was never retrieved
playwright._impl._errors.TargetClosedError: Target page, context or browser has been closed
```

thường nghĩa là một task bất đồng bộ vẫn còn dùng `page`, `context` hoặc `browser` sau khi đối tượng đó đã đóng, hoặc handler `page.on("response")` tạo task bằng `asyncio.create_task(...)` nhưng không được await/cancel đúng cách.

Service hiện quản lý Playwright theo luồng an toàn:

1. Tạo danh sách pending tasks cho response handler.
2. Gắn listener bằng handler có tên để có thể tháo ra trước cleanup.
3. Await các task bằng `asyncio.gather(..., return_exceptions=True)`.
4. Khi request bị hủy hoặc nguồn ngoài lỗi, cancel task còn pending rồi mới đóng `page`, `context`, `browser`.
5. `TargetClosedError` và Playwright timeout được ghi log cảnh báo một lần, chuyển thành warning/source status `insufficient`, `partial` hoặc `failed` tùy nguồn, không làm crash toàn bộ endpoint `analyse-one`.

Nếu frontend timeout hoặc người dùng đóng tab trong lúc crawler đang chạy, backend sẽ cleanup Playwright và re-raise cancellation cho request hiện tại; terminal không nên còn spam `Future exception was never retrieved`.

Khi bật debug:

```env
EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=true
VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=true
```

service có thể lưu thêm lỗi Playwright:

```text
reports/debug/{symbol}_vietstock_peer_playwright_error.json
reports/debug/{symbol}_vietstock_bctc_playwright_error.json
reports/debug/{symbol}_cafef_company_playwright_error.json
reports/debug/{symbol}_cafef_financial_playwright_error.json
reports/debug/{symbol}_cafef_financial_timeout.json
```

File timeout CafeF tài chính ghi `timeout_ms`, `wait_until`, `phase`, `fallback_used=true` và `report_blocked=false` để developer biết crawler đã timeout có kiểm soát. Các file này chỉ chứa source, URL, loại lỗi, phase, số task còn pending và trạng thái cleanup; không ghi token/API key. Nếu `data_sources` có `status=failed/partial/insufficient/skipped` cho CafeF/Vietstock nhưng API vẫn trả `200`, đó là lỗi nguồn ngoài, nguồn bị bỏ qua có chủ đích hoặc timeout có kiểm soát. Nếu endpoint trả `500`, service dừng hẳn, hoặc không tạo được response JSON, đó mới là lỗi service cần kiểm tra log backend.

Test nhanh từ frontend: đảm bảo preflight vẫn có `OPTIONS /api/ai-reports/analyse-one 200 OK`, sau đó gọi report với `includeExternalResearch=true`. Nếu CafeF/Vietstock chậm hoặc chặn truy cập, report vẫn trả về với warning/source status thay vì làm hỏng toàn bộ response.

Adapter không dùng OCR, không parse screenshot, không bypass paywall/captcha và không tự tạo số liệu thay thế. Nếu Vietstock thay layout, bị chặn hoặc bảng vẫn không parse được sau khi render, `data_sources` sẽ ghi `Vietstock Finance BCTC` ở trạng thái `failed` hoặc `partial`, còn phần chính của report chỉ hiển thị ghi chú mềm rằng dữ liệu BCTC công khai chưa trích xuất đủ.

Fallback peer cùng ngành từ Vietstock Finance:

```env
ENABLE_VIETSTOCK_PEER_FALLBACK=true
VIETSTOCK_PEER_URL_TEMPLATE=https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm
VIETSTOCK_PEER_TIMEOUT_MS=60000
VIETSTOCK_PEER_CACHE_TTL_SECONDS=21600
VIETSTOCK_PEER_MAX_ITEMS=10
VIETSTOCK_PEER_USE_BROWSER_FALLBACK=true
VIETSTOCK_PEER_BROWSER_HEADLESS=true
VIETSTOCK_PEER_BROWSER_WAIT_UNTIL=domcontentloaded
VIETSTOCK_PEER_BROWSER_WAIT_SELECTOR=
VIETSTOCK_PEER_BROWSER_EXTRA_WAIT_MS=5000
VIETSTOCK_PEER_BROWSER_VIEWPORT_WIDTH=1600
VIETSTOCK_PEER_BROWSER_VIEWPORT_HEIGHT=1100
VIETSTOCK_DEBUG_SAVE_RENDERED_HTML=false
VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=false

ENABLE_PEER_WEB_ENRICHMENT=true
PEER_WEB_ENRICHMENT_MAX_PEERS=10
PEER_WEB_ENRICHMENT_TIMEOUT_MS=30000
PEER_RECOMMENDATION_TOP_N=5
```

Khi Backend chưa có peer nội bộ, service thử trang `so-sanh-gia-co-phieu-cung-nganh.htm`, đọc bảng tĩnh trước rồi mới dùng Playwright nếu cần. Parser peer không đọc regex chữ in hoa từ toàn bộ trang. Peer chỉ được lấy từ bảng cùng ngành, phản hồi JSON/XHR có cấu trúc, hoặc link cổ phiếu trong dòng peer có bằng chứng rõ ràng. Các token navigation hoặc chữ thường gặp như `SPOT`, `TIN`, `DOANH`, `GIAO`, `THANH`, `TOP`, `QUY`, `THEO`, `DANH`, `VNINDEX`, `VN30` bị loại nếu không có row/table evidence.

Parser ưu tiên map theo header bảng như `Mã chứng khoán`, `Doanh nghiệp`, `Giá đóng cửa`, `% Thay đổi 1D`, `GT khớp lệnh`, `Vốn hóa`, `EPS 4 quý`, `P/E cơ bản`, `P/B`, `ROE`, `Tín hiệu mua bán`. Cột doanh nghiệp chỉ được lấy từ cell công ty hoặc link text sạch; không dùng toàn bộ text của hàng làm tên doanh nghiệp. Đây là lỗi dễ gặp khi một dòng có dạng `2 BID Ngân hàng ... Bán Bán mạnh ...` và toàn bộ chuỗi bị đẩy vào cột công ty.

Một peer chỉ được dùng khi có mã chứng khoán, source URL, bằng chứng dòng peer, không trùng chính mã đang phân tích, và có company name, hoặc ít nhất 2 chỉ tiêu định lượng, hoặc stock detail link xác thực từ bảng peer. Nếu chỉ có peer định tính, source status là `partial` và report dùng ghi chú cụ thể như `Cần bổ sung: Giá, Vốn hóa, P/B, ROE`, không biến thành khuyến nghị mua.

Khi `ENABLE_PEER_WEB_ENRICHMENT=true`, các peer thiếu dữ liệu sẽ được đối chiếu thêm theo thứ tự:

1. Backend/internal stock profile hoặc analysis-data nếu có.
2. Vietstock Finance BCTC nếu cần bổ sung chỉ tiêu tài chính.
3. CafeF BCTC/CafeF tài chính nếu fallback CafeF đang bật; dùng như nguồn đối chiếu/bổ sung và không bị bỏ qua chỉ vì Vietstock đã có dữ liệu.
4. CafeF thông tin doanh nghiệp nếu còn thiếu tên/ngành/hồ sơ.
5. Dòng peer Vietstock đã trích xuất.
6. Nguồn tin tức/nghiên cứu đáng tin cậy chỉ dùng làm bối cảnh định tính.

Nếu sau các bước này vẫn thiếu P/B, ROE, vốn hóa hoặc chỉ tiêu khác, report ghi cụ thể trường còn thiếu thay vì viết chung chung `Chưa đủ chỉ tiêu định lượng`.

Khi bật `VIETSTOCK_DEBUG_SAVE_RENDERED_HTML=true` hoặc `VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=true`, service lưu file debug vào:

```text
reports/debug/{symbol}_vietstock_bctc_rendered.html
reports/debug/{symbol}_vietstock_bctc_extraction.json
reports/debug/{symbol}_vietstock_peer_rendered.html
reports/debug/{symbol}_vietstock_peer_extraction.json
```

Các file này chỉ phục vụ kiểm tra kỹ thuật, không được nhúng vào Markdown/HTML report chính.

Khi bật `EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=true`, service cũng lưu thêm:

```text
reports/debug/{symbol}_config_check.json
reports/debug/{symbol}_backend_urls.json
reports/debug/{symbol}_cafef_company_rendered.html
reports/debug/{symbol}_cafef_company_extraction.json
reports/debug/{symbol}_cafef_financial_rendered.html
reports/debug/{symbol}_cafef_financial_extraction.json
```

Các JSON debug chứa URL đã gọi, trạng thái parser, row được nhận/loại và lý do nguồn `success/partial/failed`. Token/API key luôn được mask.

Trong request, `options.includeExternalResearch=true` cũng yêu cầu service lấy tin tức/nghiên cứu. Tin tức được chuẩn hóa gồm nguồn, tiêu đề, URL, ngày đăng, snippet, tone, relevance score, positive flags, negative flags và catalyst flags nếu phát hiện được từ keyword.

Nếu nguồn lỗi hoặc timeout, report vẫn được tạo. Response sẽ có warning và `data_sources`/`external_research_context.source_statuses` cho biết nguồn nào lỗi.

Mặc định research bỏ qua bài quá `RESEARCH_MAX_ARTICLE_AGE_DAYS=730` ngày. Khi phân tích mã `FPT`, service cũng loại các bài chỉ nói về FPT Retail/FRT nếu nội dung không thể hiện rõ chủ đề là công ty mẹ FPT.

## 5. Test bằng Postman

Method:

```http
POST http://localhost:5100/api/ai-reports/analyse-one
Content-Type: application/json
```

Body mẫu:

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "symbol": "FPT",
  "scopeExchange": "HOSE",
  "options": {
    "language": "vi",
    "riskProfile": "medium",
    "timeHorizon": "medium_term",
    "includeExternalResearch": true,
    "renderMarkdown": true,
    "renderHtml": true,
    "capitalVnd": 100000000,
    "riskPerTradePct": 1.0,
    "maxPositionPct": 12.0
  }
}
```

Response vẫn giữ shape cũ và có path thật:

```json
{
  "data": {
    "report_id": "FPT_HOSE_20260622_105312",
    "markdown_report": {
      "available": true,
      "output_path": "reports/FPT_HOSE_20260622_105312.md",
      "content": "# Báo cáo phân tích cổ phiếu FPT trên HOSE..."
    },
    "html_report": {
      "available": true,
      "output_path": "reports/FPT_HOSE_20260622_105312.html",
      "content": null,
      "template_name": "HtmlService.build"
    }
  }
}
```

## 6. Luồng xử lý chính

1. Đọc header `Authorization` từ request frontend và gọi `GET /api/watchlists` bằng token đó.
2. Xác minh mã yêu cầu nằm trong watchlists của người dùng; nếu không, dừng với `403`.
3. Ưu tiên gọi `GET /api/stocks/{symbol}/analysis-data` bằng token request.
4. Nếu `analysis-data` lỗi, fallback sang `GET /api/stocks/{symbol}` và `GET /api/stocks/{symbol}/chart?range=3m`.
5. Chuẩn hóa latest market, price history, BCTC, financial balance, VNINDEX/HoSE context, peer context và dataQuality.
6. Lấy external research nếu được bật.
7. Tính scoring định lượng bằng code.
8. Gọi OpenAI hoặc Gemini để sinh narrative theo whitelist.
9. Dựng Markdown/HTML bằng service nội bộ.
10. Ghi file UTF-8 vào `REPORT_OUTPUT_DIR`.
11. Kiểm tra final JSON bằng missing-field auditor và ghi `reports/debug/{symbol}_missing_field_audit.json` nếu bật debug.
12. Trả JSON response thống nhất.

LLM chỉ được đóng góp narrative: `strengths`, `weaknesses`, `system_decision.reasons`, narrative Markdown và `data_quality_notes`. Giá, volume, EPS, P/E, P/B, ROE, score, vùng giá và dữ liệu Backend không bị LLM ghi đè.

Response tách riêng trạng thái vận hành:

- `analysis_status`: trạng thái dựng nội dung phân tích.
- `history_status`: trạng thái lưu lịch sử AI report nếu `ENABLE_AI_REPORT_HISTORY=true`.
- `source_status`: trạng thái tổng hợp các nguồn crawler/backend.
- `report_status`: trạng thái user-facing của report. Nếu nội dung đã dựng được, lỗi nguồn phụ hoặc lỗi lưu lịch sử chỉ làm `report_status=success_with_warnings`, không chuyển toàn bộ report thành `failed`.

Chỉ dùng `report_status=failed` khi service không tạo được nội dung report.

### Data coverage khi Backend lỗi

Các flag trong `summary.data_coverage` phản ánh dữ liệu thực sự dùng được, không phản ánh việc đã thử gọi endpoint:

- `analysis_data_loaded=true` chỉ khi `/api/stocks/{symbol}/analysis-data` trả payload dùng được.
- `backend_stock_detail_loaded=true` chỉ khi `/api/stocks/{symbol}` trả payload dùng được.
- `latest_price_loaded=true` chỉ khi `latest_market` có giá/volume.
- `financials_loaded=true` chỉ khi có ít nhất một kỳ tài chính hợp lệ với tối thiểu 3 chỉ tiêu định lượng; kỳ chỉ có `period/year/quarter` không được tính.
- `financial_ratios_loaded=true` khi chỉ có nhóm chỉ số như EPS, BVPS, P/E, P/B, ROE hoặc ROA nhưng chưa đủ bộ BCTC đầy đủ.
- `price_history_points` bằng đúng số điểm chart đã nhận.
- `market_context_loaded=true` chỉ khi market context có field như VNINDEX/change/regime/score/thanh khoản hoặc alias tương đương.
- `peer_context_loaded=true` chỉ khi danh sách peers không rỗng.

Nếu cả ba stock endpoint Backend đều lỗi 500, service vẫn có thể tạo Markdown/HTML với warning rõ ràng, nhưng các flag trên phải là `false` hoặc `0` tương ứng.

`summary.report_presentation.data_coverage.items` không được có trạng thái `available` kèm value `Chưa xác minh`. Khi `status=available`, `status_label` là `Đã ghi nhận` và `value` phải là thông tin có nghĩa như `Có dữ liệu`, `3 kỳ`, `9 peer` hoặc số tin đã ghi nhận. Các trạng thái user-facing dùng mapping:

- `available`/`success` -> `Đã ghi nhận`
- `partial` -> `Ghi nhận một phần`
- `insufficient` -> `Chưa đủ dữ liệu`
- `failed` -> `Chưa lấy được`
- `missing` -> `Chưa xác minh`
- `skipped` -> `Bỏ qua`

Nguồn dữ liệu hiển thị bằng tên cụ thể: `CafeF thông tin doanh nghiệp`, `CafeF tài chính`, `Vietstock Finance BCTC`, `Vietstock peer cùng ngành`, `Danh sách theo dõi cá nhân`, `Dữ liệu giá và thanh khoản`, `Tin tức và nghiên cứu bên ngoài`. Chi tiết kỹ thuật như URL raw, `page.goto`, timeout, `periods=0` hoặc stack trace chỉ nằm trong debug.

### Chuẩn hóa Bối cảnh VNINDEX/HoSE

Backend chuẩn hóa market context trước khi dựng `summary.report_presentation.market_context_view`. Normalizer nhận cả snake_case và camelCase, ví dụ:

- `vnindex`, `vn_index`, `indexValue`, `index_value` -> `index_value`
- `changePercent`, `change_percent`, `change_pct` -> `change_percent`
- `matchedVolume`, `volume`, `totalVolume`, `liquidity` -> `liquidity`
- `tradingValueBillion`, `trading_value_billion`, `tradingValue`, `totalValue` -> `trading_value_billion`
- `totalTradingValue`, `market_value`, `value_billion`, `liquidity_value`, `matched_value` -> `trading_value_billion`
- `marketScore`, `healthScore`, `score`, `regimeScore` -> `market_health_score`

Presentation trả card user-facing cho `Chỉ số`, `Biến động`, `Thanh khoản`, `Giá trị giao dịch`, `Trạng thái` và `Điểm sức khỏe thị trường`. Nếu thiếu một field, chỉ card đó hiển thị `Chưa xác minh`; các card còn lại vẫn dùng dữ liệu đã có. Khi bật debug extraction, file `reports/debug/{symbol}_market_context_normalized.json` ghi `raw_keys_found`, `normalized` và `missing_fields`.

Card `Giá trị giao dịch` dùng số liệu có cấu trúc trước, chỉ parse từ paragraph như fallback cuối cùng và ghi warning mapping trong debug. Giá trị hiển thị theo định dạng Việt Nam, ví dụ `30.989,0 tỷ đồng`.

### Source-backed missing-field enrichment

Các field còn thiếu được xử lý theo thứ tự nguồn:

1. Backend `analysis-data`.
2. Backend stock detail/chart.
3. Vietstock Finance BCTC.
4. CafeF thông tin doanh nghiệp.
5. CafeF tài chính.
6. Vietstock peer cùng ngành.
7. Google News RSS/external research chỉ để bổ sung ngữ cảnh.

Biến cấu hình:

```env
ENABLE_SOURCE_BACKED_MISSING_FIELD_ENRICHMENT=true
MISSING_FIELD_ENRICHMENT_TIMEOUT_MS=30000
MISSING_FIELD_ENRICHMENT_MAX_ATTEMPTS=2
MISSING_FIELD_ENRICHMENT_ALLOWED_SOURCES=backend,cafef,vietstock,google_news_rss
MISSING_FIELD_ENRICHMENT_WRITE_DEBUG=true
REPORT_MISSING_VALUE_POLICY=source_backed_then_model_inference
REPORT_ALLOW_SAFE_ACTION_FALLBACK=true
REPORT_ALLOW_SAFE_SCENARIO_FALLBACK=true
REPORT_ALLOW_SAFE_CHECKLIST_FALLBACK=true
REPORT_ALLOW_MODEL_INFERENCE_FOR_QUALITATIVE_FIELDS=true
REPORT_REQUIRE_SOURCE_FOR_NUMERIC_FACTS=true
REPORT_SHOW_MISSING_REASON=true
```

`REPORT_MISSING_VALUE_POLICY=source_backed_then_model_inference` là mặc định mới. Nguyên tắc: số liệu tài chính/thị trường chỉ được điền từ nguồn đã cấu hình và có thể truy vết. Không lấy số tài chính từ website ngẫu nhiên hoặc bài tin tức. Các phần định tính như kế hoạch theo dõi, kịch bản và checklist có thể dùng model inference/fallback giáo dục an toàn từ dữ liệu đã có; fallback này không tạo giá mục tiêu, vùng dừng lỗ cụ thể hoặc tỷ trọng cá nhân hóa.

### Bắt buộc kịch bản, checklist và kế hoạch hành động

LLM prompt và backend normalizer hiện áp dụng contract bắt buộc cho các phần định tính:

- `forecast_scenarios` / `scenarios`: luôn có đúng 3 kịch bản `Tích cực`, `Cơ sở`, `Thận trọng`.
- `checklist`: luôn có ít nhất 5 mục theo dõi, mỗi mục có `label`, `status`, `note`, `source_basis`.
- `action_plan`: luôn có tối thiểu 2 mục ngắn hạn, 2 mục trung hạn, 3 điểm theo dõi và 3 nguyên tắc quản trị rủi ro.

Các cụm `Chưa xác minh`, `Chưa xác định`, `Không có dữ liệu`, `Không đủ dữ liệu`, `N/A`, `unknown`, `null`, `undefined` không được dùng làm nội dung định tính cho forecast/scenario/checklist/action plan. Nếu thiếu dữ liệu số, numeric field để `null` và phần ghi chú nêu rõ giới hạn như `Chưa có nguồn số liệu đáng tin cậy`; hệ thống không bịa giá mục tiêu, giá dừng lỗ, doanh thu, lợi nhuận hoặc tỷ lệ tài chính.

Missing-field auditor kiểm tra final response trước khi trả về và ghi từng field còn thiếu theo dạng:

```json
{
  "section": "quick_overview",
  "field": "chart_period_change",
  "display_value": "Chưa xác minh",
  "raw_data_available": true,
  "normalized_data_available": true,
  "presentation_data_available": false,
  "source_candidates": ["price_history", "stock_chart"],
  "recommended_fix": "mapping_missing"
}
```

File debug không ghi Authorization token, SQL password, OpenAI/Gemini API key hoặc JWT secret.

### Biểu đồ tài chính từ dữ liệu đang có

HTML report dựng biểu đồ tài chính từ bất kỳ series nào có ít nhất 2 điểm số hợp lệ:

- doanh thu
- lợi nhuận sau thuế hoặc lợi nhuận cổ đông mẹ
- tổng tài sản
- vốn chủ sở hữu
- ROE
- P/E
- P/B
- EPS/EPS TTM
- BVPS
- nhóm chỉ tiêu ngân hàng như thu nhập lãi thuần, cho vay khách hàng, tiền gửi khách hàng

Nếu chỉ có một kỳ, report hiển thị thẻ chỉ tiêu kỳ gần nhất thay vì báo lỗi biểu đồ. Nếu không có chỉ tiêu nào xác thực, report hiển thị empty state mềm và không tự suy diễn số liệu.

## 7. Chạy test

```powershell
cd analyse
uv run python -m compileall src
$env:PYTHONIOENCODING='utf-8'; uv run python -m pytest -q
```

Index test theo nhóm nằm ở `tests/README.md`. Khi chỉ sửa một boundary nhỏ, chạy nhóm targeted trước, sau đó vẫn chạy full pytest trước handoff/deploy.

```powershell
cd analyse
uv run ruff check .
uv run vulture src tests
```

Hai lệnh static trên là optional; nếu environment chưa có executable `ruff` hoặc `vulture`, ghi nhận là blocked và không tự cài khi chưa được cho phép.

## 7A. Phong cách báo cáo chuyên nghiệp

Markdown và HTML report hiện được dựng theo phong cách equity research memo, ưu tiên ngôn ngữ phân tích tài chính thay vì thông báo kỹ thuật. Các lỗi/giới hạn hệ thống không xuất hiện trực tiếp ở phần phân tích chính; chúng được chuyển thành ghi chú dễ hiểu cho người đọc và đặt chi tiết kỹ thuật ở phụ lục dữ liệu.

Markdown report gồm các mục chính:

- Tóm tắt điều hành
- Luận điểm chính
- Bối cảnh thị trường
- Diễn biến giá và thanh khoản
- Phân tích tài chính
- Định giá
- So sánh cùng ngành
- Mã tham khảo cùng nhóm/ngành
- Tin tức và dữ liệu bên ngoài
- Chấm điểm định lượng
- Lộ trình theo dõi
- Rủi ro chính
- Độ phủ dữ liệu và giới hạn
- Phụ lục kỹ thuật và nguồn dữ liệu

HTML report có layout self-contained gồm header tối, summary strip sticky, market context KPI cards, score cards, biểu đồ ECharts local/offline nếu có asset, bảng BCTC/peer, news cards, roadmap theo bước và phần độ phủ dữ liệu thân thiện. HTML không còn nhúng `Appendix: toàn bộ Markdown report`, không dùng CDN/JS bên ngoài theo mặc định và vẫn escape dữ liệu động để tránh inject HTML không an toàn.

Các biểu đồ trong HTML được dựng theo engine cấu hình:

- `echarts`: biểu đồ chuyên nghiệp với trục, tooltip, legend, resize responsive và dữ liệu JSON nhúng an toàn.
- `inline_svg`: fallback nhẹ nếu thiếu asset ECharts hoặc muốn HTML rất đơn giản.
- `none`: không dựng biểu đồ.

Nhóm biểu đồ chính:

- Score dashboard cho valuation, quality, growth, momentum, liquidity, size, risk và tỷ lệ tin cậy dữ liệu.
- Biểu đồ giá đóng cửa và khối lượng nếu có price history.
- Biểu đồ tài chính đa series cho kết quả kinh doanh, bảng cân đối và định giá/sinh lời nếu có ít nhất 2 kỳ hợp lệ.
- Biểu đồ peer cho vốn hóa, P/E, ROE nếu có peer định lượng.
- Gauge trạng thái thị trường nếu có regime score.

Phần bối cảnh thị trường không render raw key như `primary_index`, `change_percent`, `updated_at` hay `total_value`. Report chuyển chúng thành đoạn phân tích, KPI cards và ngày giờ Việt Nam.

News cards dùng grid responsive, card cùng hàng có chiều cao ổn định, title/snippet có line clamp và footer nguồn cố định. Ngày/giờ trong tin tức được format theo giờ Việt Nam dạng `dd/MM/yyyy HH:mm`, không hiển thị ISO timestamp raw trong phần chính.

### Cách đọc scoring và tỷ lệ tin cậy

Các điểm số là chỉ báo định lượng tham khảo, không phải khuyến nghị đầu tư cá nhân hóa:

- `valuation_score`: P/E, forward P/E, P/B, ROE nếu có.
- `quality_score`: ROE, ROS, ROAA, lợi nhuận sau thuế và số kỳ BCTC.
- `growth_score`: xu hướng doanh thu/lợi nhuận qua các kỳ BCTC.
- `momentum_score`: biến động giá trong chuỗi giá hiện có.
- `liquidity_score`: volume và giá trị giao dịch ước tính.
- `size_score`: giá trị vốn hóa nếu dữ liệu có sẵn.
- `risk_score`: beta, volatility/drawdown, bối cảnh thị trường và dữ liệu thiếu.
- `overall_score`: điểm tổng có trọng số.
- `score_confidence`: tỷ lệ tin cậy dữ liệu, không phải xác suất sinh lời. Trong Markdown/HTML, giá trị này luôn hiển thị dạng phần trăm như `60%`, không hiển thị dạng thập phân như `0.6`.

`score_confidence` bị giới hạn thấp khi thiếu dữ liệu quan trọng:

- Thiếu latest market: thường không vượt `0.55`.
- Thiếu BCTC: thường không vượt `0.60`.
- Đơn vị tài chính/market cap chưa rõ: thường không vượt `0.80`.
- Thiếu peer context: thường không vượt `0.75`.
- Không có nguồn nghiên cứu bên ngoài phù hợp: thường không vượt `0.85`.
- Nhiều cảnh báo dữ liệu nghiêm trọng: thường không vượt `0.70`.

### Cách hiển thị data quality

Ví dụ chuyển giọng văn:

- Raw kỹ thuật: `Stock chưa gắn industry_id`.
- Hiển thị chính: `Dữ liệu ngành/peer hiện chưa đủ để lập bảng so sánh định lượng đáng tin cậy.`

- Raw kỹ thuật: `Không gọi được watchlists do thiếu/sai token`.
- Hiển thị chính: `Phiên đăng nhập đã hết hạn hoặc token không hợp lệ. Vui lòng đăng nhập lại.`

Raw technical notes vẫn được giữ ở phụ lục để debug, nhưng không chen vào kết luận chính.

Các thuật ngữ kỹ thuật như `Backend`, `backend_api`, `/api/`, `payload`, `field`, `model`, `metadata`, `industry_id`, `industryPeerContext`, `financials.periods`, `missing_fields`, `filesystem`, raw endpoint path, tên collection hoặc lỗi endpoint không được hiển thị trong phần phân tích chính hoặc HTML người dùng. Nếu cần phục vụ debug, giữ trong JSON response/log hoặc báo cáo kỹ thuật riêng.

### External research trong luận điểm

Tin tức/nghiên cứu bên ngoài được nhóm thành:

- Catalyst tích cực
- Rủi ro/tín hiệu tiêu cực
- Bối cảnh trung tính
- Mục cần kiểm chứng

Mỗi nguồn dùng trong report giữ tiêu đề, nguồn, URL và ngày đăng nếu có. Service ưu tiên bài trong vòng `RESEARCH_MAX_ARTICLE_AGE_DAYS=730`, loại bài FPT Retail/FRT khi phân tích FPT nếu không liên quan công ty mẹ, và lọc các item ít giá trị phân tích như chứng quyền/static signature notices.

Phần nghiên cứu bên ngoài hiện có synthesis trước khi liệt kê bài viết. Mỗi mục tin tức được trình bày theo hướng source-aware:

- `Tóm tắt chi tiết` dựa trên tiêu đề/snippet đã thu thập; không giả vờ đã đọc full article nếu chưa fetch được nội dung đầy đủ.
- `Tác động có thể có` liên hệ tới doanh thu, biên lợi nhuận, định giá, sentiment, thanh khoản, chu kỳ ngành hoặc rủi ro.
- `Cần kiểm chứng` nhắc người đọc mở URL gốc, kiểm tra ngày đăng, doanh nghiệp liên quan và số liệu gốc.
- Badge nguồn gồm loại tín hiệu, horizon tác động và độ tin cậy.

Nếu nhiều bài trùng chủ đề, service deduplicate theo tiêu đề chuẩn hóa/source/topic để tránh lặp card nhiễu.

### Mã tham khảo cùng nhóm/ngành

Mã tham khảo chỉ được hiển thị khi Backend, Vietstock, CafeF hoặc nguồn nghiên cứu cung cấp dữ liệu đủ cơ sở. Report dùng nhãn an toàn như `Đáng theo dõi`, `Cần chờ xác nhận`, `Thiếu dữ liệu`, `Rủi ro cao`; không dùng ngôn ngữ “phải mua” hoặc khuyến nghị cá nhân hóa. Nếu thiếu peer xác thực, report nói rõ chưa đủ dữ liệu thay vì tự tạo ticker.

Ứng viên được chọn theo điểm tổng hợp mềm từ:

- cùng nhóm ngành và không trùng mã đang phân tích;
- độ đầy đủ dữ liệu sau enrichment;
- thanh khoản hoặc giá trị giao dịch;
- vốn hóa;
- định giá P/E, P/B nếu có;
- ROE/ROA hoặc chỉ tiêu sinh lời nếu có;
- tín hiệu/rủi ro kỹ thuật chỉ dùng như cảnh báo phụ;
- độ tin cậy nguồn.

Mỗi ứng viên trong report cần có lý do theo dõi, điểm mạnh, rủi ro/cần kiểm tra, dữ liệu đã có, dữ liệu còn thiếu, tỷ lệ tin cậy và nguồn. Đây là danh sách tham khảo để theo dõi tương quan cùng ngành, không phải khuyến nghị mua/bán cá nhân hóa.

Action roadmap trong HTML dùng timeline cards, trigger cần theo dõi và risk control box. Nội dung vẫn là khung tham khảo/học tập, không đưa hướng dẫn mua/bán cá nhân hóa.

## 7B. CafeF và Vietstock fallback cho dữ liệu công khai

Khi dữ liệu nội bộ chưa đủ, `analyse` có thể đối chiếu thêm nguồn công khai theo thứ tự thận trọng:

1. Backend `analysis-data`.
2. CafeF company overview.
3. Vietstock Finance BCTC.
4. CafeF BCTC như nguồn fallback sau Vietstock.
5. Vietstock peer cùng ngành tab `Tổng quan`.
6. External research chỉ dùng làm bối cảnh định tính.

Các nguồn này không được dùng để bịa số liệu. Nếu trang nguồn đổi layout, bị chặn hoặc không trả bảng có cấu trúc đủ tin cậy, report giữ trạng thái thiếu dữ liệu chuyên nghiệp và không đánh dấu phần đó là đã tải thành công.

### CafeF company overview

CafeF company fallback dùng URL:

```text
https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn
```

Ví dụ:

```text
https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn
```

Cấu hình:

```env
ENABLE_CAFEF_COMPANY_FALLBACK=true
CAFEF_COMPANY_URL_TEMPLATE=https://cafef.vn/du-lieu/{exchange}/{symbol}-ban-lanh-dao-so-huu.chn
CAFEF_COMPANY_TIMEOUT_MS=30000
CAFEF_COMPANY_CACHE_TTL_SECONDS=21600
CAFEF_COMPANY_USE_BROWSER_FALLBACK=true
```

Adapter thử HTML tĩnh trước, sau đó dùng Playwright nếu trang cần render bằng trình duyệt. Dữ liệu dùng được gồm tên doanh nghiệp, ngành/nhóm ngành, mô tả kinh doanh, lãnh đạo và sở hữu nếu trang CafeF cung cấp rõ ràng. Phần “Tổng quan doanh nghiệp” sẽ ưu tiên dữ liệu này khi Backend chưa có mô tả đủ sâu hoặc chưa có dữ liệu quản trị/sở hữu.

### CafeF BCTC

CafeF financial fallback dùng URL:

```text
https://cafef.vn/du-lieu/{exchange}/{symbol}-tai-chinh.chn
```

Ví dụ:

```text
https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn
```

Cấu hình:

```env
ENABLE_CAFEF_FINANCIAL_FALLBACK=true
CAFEF_FINANCIAL_URL_TEMPLATE=https://cafef.vn/du-lieu/{exchange}/{symbol}-tai-chinh.chn
CAFEF_FINANCIAL_TIMEOUT_MS=90000
CAFEF_FINANCIAL_CACHE_TTL_SECONDS=21600
CAFEF_FINANCIAL_MAX_PERIODS=8
CAFEF_FINANCIAL_UNIT=Tỷ đồng
CAFEF_FINANCIAL_USE_BROWSER_FALLBACK=true

ENABLE_FINANCIAL_SOURCE_MERGE=true
FINANCIAL_SOURCE_PRIORITY=backend_analysis_data,vietstock_bctc,cafef_financial
FINANCIAL_ALLOW_SUPPLEMENTARY_BACKFILL=true
FINANCIAL_CONFLICT_TOLERANCE_PCT=5
FINANCIAL_REQUIRE_SOURCE_FOR_BACKFILL=true
FINANCIAL_BACKFILL_WRITE_DEBUG=true
```

Một kỳ tài chính chỉ được xem là hợp lệ khi có tối thiểu 3 chỉ tiêu định lượng có ý nghĩa. Với ngân hàng, parser nhận diện các chỉ tiêu như thu nhập lãi thuần, thu nhập dịch vụ thuần, thu nhập kinh doanh, thu nhập khác, chi phí hoạt động, lợi nhuận trước/sau thuế, tổng tài sản, cho vay khách hàng, tiền gửi khách hàng, vốn chủ, EPS, BVPS, ROE, ROA, NIM, nợ xấu, CASA, CIR. Với doanh nghiệp thường, parser nhận diện doanh thu, lợi nhuận gộp, LNTT, LNST, tài sản, nợ phải trả, vốn chủ, tiền và tương đương tiền, tồn kho, nợ vay ngắn/dài hạn, dòng tiền HĐKD/đầu tư/tài chính, EPS, BVPS, ROE, ROA, biên lợi nhuận và nợ/VCSH.

CafeF có thể chậm vì trang tải quảng cáo, tracking hoặc request nền lâu hơn nội dung chính. Với trang tài chính CafeF, Playwright dùng `wait_until="domcontentloaded"` thay vì `networkidle` để không chờ vô hạn các request nền. Sau DOM ready, crawler chỉ chờ selector/nội dung mục tiêu trong thời gian ngắn rồi parse phần có sẵn.

`CAFEF_FINANCIAL_TIMEOUT_MS` mặc định là `90000`. Nếu biến này thiếu hoặc cấu hình không hợp lệ, service tự fallback về `90000`. Nếu CafeF timeout, adapter trả `periods=[]` và warning ngắn; lớp report ghi source `CafeF tài chính` là `failed` cho timeout hoặc `insufficient` khi trang tải được nhưng không có kỳ tài chính chuẩn hóa. Report không crash và không hiển thị URL/timeout kỹ thuật trong `data_sources`.

Luồng ưu tiên BCTC hợp nhất là:

1. Backend/internal BCTC nếu đã có kỳ hợp lệ.
2. Vietstock Finance BCTC nếu Backend/internal còn thiếu và Vietstock lấy được `periods > 0`.
3. CafeF tài chính là nguồn đối chiếu/bổ sung và vẫn được thử khi `ENABLE_CAFEF_FINANCIAL_FALLBACK=true`.

Merge layer giữ giá trị từ nguồn ưu tiên cao hơn. CafeF chỉ bù field/kỳ còn thiếu hoặc thêm kỳ chưa có nếu kỳ đó đủ chỉ tiêu định lượng. Nếu CafeF có cùng field/kỳ với Backend/Vietstock, service không ghi đè; nếu chênh lệch vượt `FINANCIAL_CONFLICT_TOLERANCE_PCT`, conflict được ghi vào debug và giữ giá trị primary. Mỗi field được CafeF bù có source metadata và xuất hiện trong `financial_source_contributions`.

CafeF tài chính không bị `skipped` chỉ vì Vietstock Finance đã thành công. Nếu CafeF bù được field thiếu, source user-facing ghi `Đã ghi nhận` và detail nêu số chỉ tiêu/kỳ đã bù. Nếu CafeF chỉ cung cấp dữ liệu đối chiếu nhưng không bù thêm field, status là `Ghi nhận một phần`. Nếu CafeF không có metric chuẩn hóa, user-facing source là `Chưa đủ dữ liệu`. Nếu CafeF timeout, user-facing source là `Chưa lấy được`. Trường hợp `skipped` chỉ dùng khi nguồn bị tắt bởi cấu hình, người dùng tắt hoặc chính sách backoff/rate-limit; chi tiết URL, timeout, `page.goto`, `periods=0` chỉ nằm trong debug/log.

Khi bật debug extraction, service ghi:

```text
reports/debug/{symbol}_cafef_financial_attempt.json
reports/debug/{symbol}_cafef_financial_audit.json
reports/debug/{symbol}_financial_backfill_report.json
```

Các artifact này chứa trạng thái tải trang, số bảng, kỳ, metric đã map/chưa map, contribution bù dữ liệu, conflict và field chưa bù được. Không ghi token/API key/SQL password.

### Vietstock peer tab Tổng quan

Peer fallback dùng URL:

```text
https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm
```

Ví dụ:

```text
https://finance.vietstock.vn/CMG/so-sanh-gia-co-phieu-cung-nganh.htm
```

Cấu hình:

```env
ENABLE_VIETSTOCK_PEER_FALLBACK=true
VIETSTOCK_PEER_URL_TEMPLATE=https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm
VIETSTOCK_PEER_TIMEOUT_MS=60000
VIETSTOCK_PEER_CACHE_TTL_SECONDS=21600
VIETSTOCK_PEER_MAX_ITEMS=10
VIETSTOCK_PEER_USE_BROWSER_FALLBACK=true
VIETSTOCK_PEER_DEFAULT_TAB=Tổng quan
```

Default report chỉ dùng tab `Tổng quan`. Parser nhận diện hàng peer từ bảng có header như `Mã chứng khoán`, `Giá đóng cửa`, `% Thay đổi 1D`, `KL khớp lệnh`, `GT khớp lệnh`, `Vốn hóa`, `EPS 4 quý`, `P/E cơ bản`, `MACD`, `RSI`, `Điểm cơ bản`. Không dùng regex quét toàn trang để lấy chữ in hoa làm ticker, vì cách đó dễ lấy nhầm các từ điều hướng như `SPOT`, `TIN`, `DOANH`, `GIAO`, `THANH`, `TOP`, `QUY`, `THEO`, `DANH`.

Peer hợp lệ phải có mã chứng khoán, evidence từ hàng bảng hoặc JSON có cấu trúc, source URL, không trùng mã đang phân tích và có tối thiểu 2 chỉ tiêu định lượng hữu ích. Nếu chỉ có link/tên mà thiếu dữ liệu định lượng, report không dựng bảng peer định lượng.

HTML peer table hiển thị các cột:

```text
Mã | Doanh nghiệp | Giá | % 1D | KL khớp lệnh | GT khớp lệnh | Vốn hóa | EPS 4Q | P/E | Xếp hạng | Tín hiệu | RSI | Nhận xét
```

Khi dữ liệu chart gốc trên Vietstock không truy cập được dưới dạng DOM/JSON an toàn, HTML tự dựng chart nội bộ từ bảng peer đã trích xuất, ví dụ market cap, P/E và RSI. Service không dùng ảnh chụp màn hình hoặc OCR.

### Layout BCTC, chart tài chính và kiểm tra mapping

Phần `Phân tích tài chính` trong HTML không đặt bảng BCTC rộng và biểu đồ vào cùng một grid hai cột. Cấu trúc chuẩn là:

```html
<div class="table-scroll financial-table-scroll">
  <table class="data-table financial-table">...</table>
</div>
<div class="financial-charts-grid">...</div>
<div class="balance-health-card">...</div>
```

Quy tắc vận hành:

- Bảng BCTC luôn nằm trong `.table-scroll` để cuộn ngang khi mở bằng browser hoặc `file:///`.
- `.financial-grid` không được dùng cho bảng BCTC và chart tài chính.
- Biểu đồ ưu tiên ECharts local/offline khi có `src/analyse/assets/echarts.min.js`; nếu thiếu asset thì dùng inline SVG fallback để HTML vẫn standalone.
- Nếu chỉ có một kỳ tài chính, report hiển thị metric card thay vì cố dựng line chart.
- Nếu có tối thiểu 2 điểm hợp lệ cho một chỉ tiêu, report dựng chart từ engine đang bật và không tự suy diễn điểm thiếu.

Parser BCTC map theo nhãn dòng và ngữ cảnh chỉ tiêu. Với ngân hàng:

- `Tỷ suất sinh lợi trên tổng tài sản bình quân (ROAA)` map sang `roa`, không map sang `total_assets`.
- `Tổng cộng tài sản`/`Tổng tài sản` map sang `total_assets`.
- `Vốn chủ sở hữu` map sang `equity`.
- Các chỉ tiêu ngân hàng như `Cho vay khách hàng`, `Tiền gửi khách hàng`, `Tiền gửi tại NHNN`, `Chứng khoán đầu tư`, `Phát hành giấy tờ có giá` được ưu tiên trong bảng sức khỏe cân đối.

Sanity check dữ liệu ngân hàng:

- Nếu `0 < total_assets < 1000`, giá trị bị xem là đáng ngờ và không hiển thị như tổng tài sản.
- Nếu `customer_loans` hoặc `customer_deposits` lớn hơn `total_assets * 1.2`, chỉ tiêu bị đánh dấu chưa xác minh.
- Nếu `equity > total_assets`, vốn chủ sở hữu bị loại khỏi phần định lượng.
- Nếu `ROA > 20` hoặc `ROE > 50`, chỉ tiêu bị xem là bất thường.

Khi một giá trị bị loại, phần chính của report hiển thị `Chưa xác minh`; chi tiết kỹ thuật nằm ở phụ lục/debug artifacts.

### Peer định lượng và peer định tính

Vietstock peer tab `Tổng quan` có thể trả:

- Bảng định lượng đầy đủ: report hiển thị bảng peer và biểu đồ peer.
- Chỉ ticker + tên doanh nghiệp từ dòng/link đã xác thực: report hiển thị card peer định tính với nhãn `Cần chờ xác nhận`.
- Không có dòng peer dùng được: source status hiển thị `Chưa trích xuất đủ`.

Peer định tính không được xem là khuyến nghị mua và không được dùng để tạo kết luận định giá mạnh. Mã đang phân tích luôn bị loại khỏi danh sách `Mã tham khảo cùng nhóm/ngành`.

### Debug artifacts

Chỉ bật khi cần kiểm tra kỹ thuật:

```env
EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML=true
EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=true
```

File debug có thể xuất ra:

```text
reports/debug/{symbol}_config_check.json
reports/debug/{symbol}_backend_urls.json
reports/debug/{symbol}_cafef_company_request.json
reports/debug/{symbol}_cafef_company_raw.html
reports/debug/{symbol}_cafef_company_rendered.html
reports/debug/{symbol}_cafef_company_tables.json
reports/debug/{symbol}_cafef_company_extraction.json
reports/debug/{symbol}_leadership_ownership_merge.json
reports/debug/{symbol}_market_context_normalized.json
reports/debug/{symbol}_cafef_financial_attempt.json
reports/debug/{symbol}_cafef_financial_rendered.html
reports/debug/{symbol}_cafef_financial_extraction.json
reports/debug/{symbol}_vietstock_bctc_rendered.html
reports/debug/{symbol}_vietstock_bctc_extraction.json
reports/debug/{symbol}_vietstock_peer_request.json
reports/debug/{symbol}_vietstock_peer_raw.html
reports/debug/{symbol}_vietstock_peer_rendered.html
reports/debug/{symbol}_vietstock_peer_tables.json
reports/debug/{symbol}_vietstock_peer_extraction.json
reports/debug/{symbol}_vietstock_peer_raw_rows.json
reports/debug/{symbol}_vietstock_peer_normalized.json
reports/debug/{symbol}_peer_enrichment.json
reports/debug/{symbol}_same_industry_candidates.json
reports/debug/{symbol}_source_backed_evidence.json
reports/debug/{symbol}_research_queries.json
reports/debug/{symbol}_article_extraction.json
reports/debug/{symbol}_forecast_scenarios.json
reports/debug/{symbol}_missing_value_policy.json
reports/debug/{symbol}_llm_prompt_input_evidence.json
reports/debug/{symbol}_mandatory_forecast_sections_validation.json
```

Các artifact này không được nhúng vào report chính.

### CafeF ban lãnh đạo, sở hữu và Vietstock peer

CafeF thông tin doanh nghiệp dùng URL:

```text
https://cafef.vn/du-lieu/{exchange_lower}/{symbol_lower}-ban-lanh-dao-so-huu.chn
```

`{exchange}` và `{symbol}` trong cấu hình luôn được service tự chuyển về lowercase khi gọi CafeF, ví dụ `VCB`/`HOSE` thành `https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn`. Adapter ưu tiên HTML tĩnh, sau đó đọc các endpoint công khai mà trang CafeF dùng để nạp dữ liệu như `CompanyIntro.ashx`, `ListCeo.ashx` và `CoCauSoHuu.ashx`. Nếu vẫn chưa đủ dữ liệu, service mới dùng Playwright để render trang và kiểm tra DOM/response động.

Parser chỉ nhận các trường đã xác minh được từ nguồn công khai: tên doanh nghiệp, sàn, nhóm ngành nếu có, ban lãnh đạo và sở hữu/cổ đông. Các dòng menu, header, footer hoặc text điều hướng không được dùng làm tên doanh nghiệp hay tên cổ đông. Nếu chỉ lấy được tên doanh nghiệp nhưng không có ban lãnh đạo/cổ đông, source status là `partial`; nếu trang tải được nhưng không có dữ liệu hữu ích, status là `insufficient`.

Vietstock peer cùng ngành dùng URL:

```text
https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm
```

Tab mặc định là `Tổng quan`. Adapter đọc bảng HTML theo header/cell và cũng kiểm tra dữ liệu JSON/DOM sau khi Playwright render, bao gồm trường hợp Vietstock gộp mã và tên doanh nghiệp trong cùng một ô. Trường `Doanh nghiệp` trong report chỉ chứa tên công ty, không chứa cả dòng số liệu.

Luồng enrichment peer:

1. Backend/internal stock endpoint nếu có dữ liệu.
2. Vietstock Finance BCTC nếu cần bổ sung chỉ tiêu tài chính.
3. CafeF BCTC/CafeF tài chính là nguồn đối chiếu nếu fallback CafeF đang bật; không bị bỏ qua chỉ vì Vietstock đã có kỳ BCTC.
4. CafeF thông tin doanh nghiệp nếu còn thiếu tên/ngành/hồ sơ.
5. Dòng peer Vietstock đã trích xuất.

Service chỉ làm giàu các chỉ tiêu có nguồn xác minh được như giá, vốn hóa, EPS, P/E, P/B, ROE, ROA và thanh khoản. Nếu sau enrichment vẫn thiếu dữ liệu, report ghi rõ chỉ tiêu nào còn thiếu thay vì dùng một câu chung chung. `Mã tham khảo cùng nhóm/ngành` là danh sách để theo dõi, không phải khuyến nghị mua/bán cá nhân hóa.

Để kiểm tra khi thiếu ban lãnh đạo/cổ đông hoặc peer, bật:

```env
EXTERNAL_DATA_DEBUG_SAVE_RENDERED_HTML=true
EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=true
VIETSTOCK_DEBUG_SAVE_RENDERED_HTML=true
VIETSTOCK_DEBUG_SAVE_EXTRACTION_JSON=true
```

Sau đó xem `reports/debug/{symbol}_cafef_company_tables.json`, `reports/debug/{symbol}_leadership_ownership_merge.json`, `reports/debug/{symbol}_market_context_normalized.json`, `reports/debug/{symbol}_cafef_financial_attempt.json`, `reports/debug/{symbol}_vietstock_peer_tables.json` và `reports/debug/{symbol}_vietstock_peer_normalized.json` để biết bảng/row nào được tìm thấy, dòng nào bị loại và lý do.

### Cách test nhanh các mã mẫu

Gọi API public như bình thường và đổi `symbol`/`scopeExchange`:

- `VCB`/`HOSE`: kiểm tra CafeF overview, CafeF BCTC ngân hàng và peer ngân hàng.
- `CMG`/`HOSE`: kiểm tra Vietstock peer công nghệ tab `Tổng quan`.
- `HPG`/`HOSE`: kiểm tra BCTC doanh nghiệp thường và tin ngành thép nếu external research bật.
- `AAA`/`HOSE`: kiểm tra parser doanh nghiệp thường và peer/nhựa nếu nguồn công khai có dữ liệu.

Tỷ lệ tin cậy trong Markdown/HTML luôn hiển thị dạng phần trăm như `60%`, không hiển thị dạng thập phân như `0.6`. Các thuật ngữ kỹ thuật nội bộ không xuất hiện trong phần chính của report.

## 8. Troubleshooting

- Không có file report: kiểm tra `REPORT_RENDER_MARKDOWN`, `REPORT_RENDER_HTML`, quyền ghi thư mục và `warnings`.
- Backend báo `All connection attempts failed`: gọi `/api/analyse/config-check?checkBackend=true`, kiểm tra `BACKEND_API_BASE_URL` có scheme `http://`/`https://`, Backend có đang chạy không và URL không bị `/api/api`.
- CafeF company name bị dính menu: parser hiện chỉ nhận tên doanh nghiệp sạch; nếu không sạch, nguồn được đánh dấu `partial` và không ghi đè tên công ty hiện có.
- CafeF BCTC chỉ `partial`: nguồn chỉ có ratio hoặc chỉ nhận diện kỳ, chưa đủ bộ BCTC định lượng đầy đủ.
- Chart tài chính không xuất hiện: cần ít nhất 2 điểm số hợp lệ trong cùng một chỉ tiêu; một kỳ sẽ chỉ hiển thị metric cards.
- Vietstock peer `peers=0`: trang có thể render động hoặc không có bảng peer định lượng; bật Playwright/debug để kiểm tra file `reports/debug`.
- `html_report.content=null`: đây là mặc định khi `REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false`; mở file theo `html_report.output_path`.
- Watchlist 401: frontend cần gửi header `Authorization` chứa token phiên đăng nhập hiện tại. Không copy user token vào `.env`; nếu token hết hạn, đăng nhập lại rồi gọi lại report.
- Symbol bị từ chối: mã không nằm trong watchlists của user đang đăng nhập hoặc khác sàn nếu watchlist có thông tin sàn. Thêm mã vào watchlists rồi gọi lại.
- Financials vẫn thiếu: gọi trực tiếp `/api/stocks/FPT/analysis-data?...` bằng Postman và kiểm tra `data.financials.periods`; nếu rỗng, kiểm tra tiếp `ENABLE_VIETSTOCK_FINANCIAL_FALLBACK=true`, mạng internet và phụ lục kỹ thuật của report để biết Vietstock có trả bảng HTML parse được hay không.
- Market/peer vẫn rỗng: kiểm tra `data.hoseMarketContext`, `data.industryPeerContext.peers` và `data.dataQuality.missingFields` từ Backend.
- Scores vẫn null: kiểm tra `ENABLE_SCORING=true`; nếu input thiếu nhiều, score vẫn là điểm partial với tỷ lệ tin cậy thấp.
- External research rỗng: kiểm tra `ENABLE_EXTERNAL_RESEARCH`, `ENABLE_GOOGLE_NEWS_RSS`, kết nối mạng, cache TTL và query symbol/company.
- Research adapter disabled: bật `ENABLE_VIETSTOCK=true`, `ENABLE_CAFEF=true`, `ENABLE_GOOGLE_NEWS_RSS=true`, `RESEARCH_GOOGLE_NEWS_RSS_ENABLED=true`.
- Vietstock/CafeF rỗng: service đang dùng Google News RSS có lọc domain; nếu Google News chưa index bài hoặc nguồn chặn truy cập công khai thì kết quả có thể trống.
- CORS preflight với token: kiểm tra `Access-Control-Request-Headers: authorization,content-type`; cấu hình mặc định `allow_headers=["*"]` cho phép header `Authorization`.

## 9. Test trực tiếp Backend analysis-data bằng Postman

```http
GET http://localhost:5000/api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Kỳ vọng trong `data` có:

```json
{
  "latestMarket": {},
  "priceHistory": [],
  "financials": { "periods": [] },
  "financialBalance": {},
  "hoseMarketContext": {},
  "industryPeerContext": { "peers": [] },
  "dataQuality": { "warnings": [] }
}
```

## Lưu lịch sử báo cáo AI bằng SQL Server

Frontend không gửi `userId` khi tạo hoặc đọc lịch sử báo cáo. Frontend chỉ gửi token đăng nhập hiện tại:

```http
Authorization: <scheme> <access_token>
```

Trong cấu hình mặc định, `<scheme>` là `Bearer`.

Luồng định danh:

1. Frontend gọi `POST /api/ai-reports/analyse-one` hoặc các endpoint history của `analyse`.
2. `analyse` đọc token từ header.
3. `analyse` gọi Backend chính `GET /api/users/me` bằng chính token đó.
4. Backend MongoDB xác thực JWT và trả user hiện tại.
5. `analyse` lấy `mongo_user_id` từ `data.id`.
6. `analyse` vẫn gọi `GET /api/watchlists` bằng token để xác minh mã nằm trong watchlist.
7. Nếu bật lưu lịch sử, `analyse` lưu report JSON vào SQL Server với `mongo_user_id`.

MongoDB trong `api` vẫn là nguồn dữ liệu chính cho user, auth, watchlists và stocks. SQL Server trong `analyse` chỉ lưu lịch sử báo cáo AI đã tạo, không lưu token, refresh token, password hash hoặc API key.

### Env

```env
# Backend identity resolution
BACKEND_CURRENT_USER_ENDPOINT=/api/users/me

# AI report history
ENABLE_AI_REPORT_HISTORY=false
AI_REPORT_DB_URL=mssql+pyodbc://<db-user>:<db-secret>@localhost:1433/AIStockAnalysis?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
AI_REPORT_HISTORY_SAVE_FAILURE_POLICY=non_blocking
```

Mặc định `ENABLE_AI_REPORT_HISTORY=false` để local dev không bị lỗi nếu chưa có SQL Server. Khi tắt history, `analyse-one` vẫn chạy bình thường, không lưu lịch sử và trả `history_status="disabled"`. Các endpoint history trả lỗi sạch `503` với `error.type="HISTORY_DISABLED"`.

Khi bật history nhưng SQL Server lỗi hoặc bảng chưa có migration, các endpoint history trả `503` với `error.type="HISTORY_UNAVAILABLE"` và không trả connection string. Với `analyse-one`, policy `non_blocking` cho phép report vẫn trả về kèm `history_status="failed"` và warning: `Báo cáo đã phân tích thành công nhưng chưa lưu được lịch sử.` Với policy `strict`, report generation thành công nhưng save history lỗi sẽ trả lỗi có kiểm soát `HISTORY_SAVE_FAILED`.

`created_at` trong bảng `ai_report_histories` dùng `SYSUTCDATETIME()`, nghĩa là lưu theo UTC. Frontend nên convert sang `Asia/Ho_Chi_Minh` hoặc timezone người dùng khi hiển thị, không giả định đây là giờ local.

### Migration SQL Server

File migration:

```text
analyse/migrations/sqlserver/001_create_ai_report_histories.sql
```

Chạy script này bằng SSMS, Azure Data Studio hoặc `sqlcmd` trên database `AIStockAnalysis` trước khi bật `ENABLE_AI_REPORT_HISTORY=true`.

Bảng chính:

```text
ai_report_histories
```

Bảng lưu `mongo_user_id`, `mongo_watchlist_id`, `mongo_stock_id`, `symbol`, `exchange`, metadata provider/model/score và `report_json` đầy đủ để frontend render lại bằng template hiện tại.

### API history

List:

```http
GET http://localhost:5100/api/ai-reports/history
Authorization: <scheme> <access_token>
```

Filter hỗ trợ:

```text
symbol
exchange
provider
model
fromDate
toDate
page
limit
```

Detail:

```http
GET http://localhost:5100/api/ai-reports/history/{id}
Authorization: <scheme> <access_token>
```

Delete:

```http
DELETE http://localhost:5100/api/ai-reports/history/{id}
Authorization: <scheme> <access_token>
```

Mọi query list/detail/delete đều resolve user từ token rồi filter SQL Server bằng `mongo_user_id`. User không thể đọc hoặc xóa report của user khác nếu `mongo_user_id` không khớp.

### Test nhanh bằng Postman

1. Bật env:

```env
ENABLE_AI_REPORT_HISTORY=true
AI_REPORT_DB_URL=<masked-sql-server-connection-string>
BACKEND_CURRENT_USER_ENDPOINT=/api/users/me
```

2. Chạy migration SQL.
3. Gọi `POST /api/ai-reports/analyse-one` với token user hợp lệ và mã nằm trong watchlist.
4. Kiểm tra response có `data.history_id`.
5. Gọi `GET /api/ai-reports/history` bằng cùng token.
6. Gọi `GET /api/ai-reports/history/{history_id}` và dùng `data.report_json` để render lại report.
7. Gọi `DELETE /api/ai-reports/history/{history_id}` nếu cần xóa.

### Lưu ý bảo mật

- Không gửi `userId` từ frontend.
- Không tin `userId` nếu client tự thêm vào body/query.
- Không lưu token vào SQL Server.
- Không log raw token.
- Không lưu OpenAI/Gemini API key vào SQL Server.
- Không log hoặc dán raw `AI_REPORT_DB_URL`; diagnostic/log chỉ được dùng URL đã mask password bằng `safe_db_url_for_log(...)` hoặc giá trị tương đương.
- `user_email` trong SQL Server chỉ là metadata hỗ trợ tra cứu; khóa phân quyền là `mongo_user_id`.
