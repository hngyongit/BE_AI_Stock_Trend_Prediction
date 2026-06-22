# Dịch vụ `analyse`

`analyse` là dịch vụ Python/FastAPI tạo báo cáo phân tích cổ phiếu Việt Nam bằng dữ liệu Backend và phần diễn giải LLM có kiểm soát. Endpoint chính:

```http
POST /api/ai-reports/analyse-one
```

Báo cáo này chỉ phục vụ tham khảo/học tập, không phải khuyến nghị đầu tư cá nhân hóa.

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

## 2. Cấu hình Backend và LLM

Các biến chính trong `.env`:

```env
BACKEND_API_BASE_URL=http://localhost:5000
BACKEND_API_TOKEN=
BACKEND_API_AUTH_SCHEME=Bearer

BACKEND_USE_ANALYSIS_DATA_ENDPOINT=true
BACKEND_ANALYSIS_DATA_ENDPOINT=/api/stocks/{symbol}/analysis-data
BACKEND_ANALYSIS_DATA_QUARTERS=6
BACKEND_ANALYSIS_DATA_CHART_RANGE=3m
BACKEND_ANALYSIS_DATA_INCLUDE_PEERS=true
BACKEND_ANALYSIS_DATA_INCLUDE_MARKET_CONTEXT=true
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

### Lấy token Backend cho watchlist

`/api/watchlists` là optional nếu `BACKEND_WATCHLIST_REQUIRED=false`. Nếu muốn dùng watchlist, login Backend:

```http
POST http://localhost:5000/api/auth/login
Content-Type: application/json
```

```json
{
  "email": "admin@example.com",
  "password": "admin123456"
}
```

Sau đó copy `access_token` vào:

```env
BACKEND_API_TOKEN=<access_token>
BACKEND_API_AUTH_SCHEME=Bearer
```

Nếu token trong `.env` đã có dạng `Bearer <token>`, service sẽ gửi nguyên trạng và không lặp `Bearer`.

### Cấu hình scoring

```env
ENABLE_SCORING=true
SCORING_MIN_FINANCIAL_PERIODS=3
SCORING_REQUIRE_FINANCIALS_FOR_OVERALL=false
SCORING_ENABLE_MARKET_CONTEXT=true
SCORING_ENABLE_PEER_CONTEXT=true
```

Scoring là chỉ báo định lượng tham khảo, không phải khuyến nghị đầu tư cá nhân hóa.

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
REPORT_WRITE_MARKDOWN=true
REPORT_WRITE_HTML=true
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
REPORT_WRITE_MARKDOWN=true
REPORT_WRITE_HTML=true
REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE=true
REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false
```

`REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false` giúp response JSON nhẹ hơn, nhưng file HTML vẫn được ghi ra ổ đĩa.

Kiểm tra file đã tạo:

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\analyse
ls reports
start reports\FPT_HOSE_20260622_105312.html
```

Nếu không thấy file, kiểm tra `warnings` và `data_sources` trong response để biết lỗi ghi Markdown/HTML.

## 4. Bật external research/news

External research dùng nguồn công khai, chủ yếu qua Google News RSS. Vietstock và CafeF được hỗ trợ bằng truy vấn Google News RSS có lọc domain `site:vietstock.vn` và `site:cafef.vn`; service không bypass paywall, login wall hoặc cơ chế anti-bot.

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
RESEARCH_SOURCE_PRIORITY=vietstock.vn,cafef.vn,tinnhanhchungkhoan.vn,vneconomy.vn,bnews.vn
```

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

1. Gọi `GET /api/watchlists` nếu có token; lỗi 401 không chặn phân tích khi `BACKEND_WATCHLIST_REQUIRED=false`.
2. Ưu tiên gọi `GET /api/stocks/{symbol}/analysis-data`.
3. Nếu `analysis-data` lỗi, fallback sang `GET /api/stocks/{symbol}` và `GET /api/stocks/{symbol}/chart?range=3m`.
4. Chuẩn hóa latest market, price history, BCTC, financial balance, VNINDEX/HoSE context, peer context và dataQuality.
5. Lấy external research nếu được bật.
6. Tính scoring định lượng bằng code.
7. Gọi OpenAI hoặc Gemini để sinh narrative theo whitelist.
8. Dựng Markdown/HTML bằng service nội bộ.
9. Ghi file UTF-8 vào `REPORT_OUTPUT_DIR`.
10. Trả JSON response thống nhất.

LLM chỉ được đóng góp narrative: `strengths`, `weaknesses`, `system_decision.reasons`, narrative Markdown và `data_quality_notes`. Giá, volume, EPS, P/E, P/B, ROE, score, vùng giá và dữ liệu Backend không bị LLM ghi đè.

### Data coverage khi Backend lỗi

Các flag trong `summary.data_coverage` phản ánh dữ liệu thực sự dùng được, không phản ánh việc đã thử gọi endpoint:

- `analysis_data_loaded=true` chỉ khi `/api/stocks/{symbol}/analysis-data` trả payload dùng được.
- `backend_stock_detail_loaded=true` chỉ khi `/api/stocks/{symbol}` trả payload dùng được.
- `latest_price_loaded=true` chỉ khi `latest_market` có giá/volume.
- `financials_loaded=true` chỉ khi `financials.periods` có ít nhất một kỳ.
- `price_history_points` bằng đúng số điểm chart đã nhận.
- `market_context_loaded=true` chỉ khi market context có field như VNINDEX/change/regime.
- `peer_context_loaded=true` chỉ khi danh sách peers không rỗng.

Nếu cả ba stock endpoint Backend đều lỗi 500, service vẫn có thể tạo Markdown/HTML với warning rõ ràng, nhưng các flag trên phải là `false` hoặc `0` tương ứng.

## 7. Chạy test

```powershell
cd analyse
python -m pytest
```

Hoặc:

```powershell
cd analyse
uv run pytest
```

## 8. Troubleshooting

- Không có file report: kiểm tra `REPORT_WRITE_MARKDOWN`, `REPORT_WRITE_HTML`, quyền ghi thư mục và `warnings`.
- `html_report.content=null`: đây là mặc định khi `REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false`; mở file theo `html_report.output_path`.
- Watchlist 401: login Backend, copy `access_token` vào `BACKEND_API_TOKEN`, restart `analyse`. Nếu `BACKEND_WATCHLIST_REQUIRED=false`, phân tích vẫn tiếp tục bằng `analysis-data`.
- Financials vẫn thiếu: gọi trực tiếp `/api/stocks/FPT/analysis-data?...` bằng Postman và kiểm tra `data.financials.periods`; nếu rỗng thì Mongo/API chưa có BCTC cho mã đó.
- Market/peer vẫn rỗng: kiểm tra `data.hoseMarketContext`, `data.industryPeerContext.peers` và `data.dataQuality.missingFields` từ Backend.
- Scores vẫn null: kiểm tra `ENABLE_SCORING=true`; nếu input thiếu nhiều, score vẫn là điểm partial với `score_confidence` thấp.
- External research rỗng: kiểm tra `ENABLE_EXTERNAL_RESEARCH`, `ENABLE_GOOGLE_NEWS_RSS`, kết nối mạng, cache TTL và query symbol/company.
- Research adapter disabled: bật `ENABLE_VIETSTOCK=true`, `ENABLE_CAFEF=true`, `ENABLE_GOOGLE_NEWS_RSS=true`, `RESEARCH_GOOGLE_NEWS_RSS_ENABLED=true`.
- Vietstock/CafeF rỗng: service đang dùng Google News RSS có lọc domain; nếu Google News chưa index bài hoặc nguồn chặn truy cập công khai thì kết quả có thể trống.
- Symbol bị từ chối: nếu `ANALYSE_ONE_SYMBOL_ONLY=true`, symbol phải nằm trong nhóm watchlist hợp lệ sau khi giới hạn `MAX_WATCHLIST_SYMBOLS`.

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
