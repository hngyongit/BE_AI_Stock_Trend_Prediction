# Báo cáo fix `analyse`: dùng API analysis-data, map đủ field và tính scoring

## 1. Mục tiêu triển khai

Mục tiêu là cập nhật service `analyse` để ưu tiên dùng Backend endpoint mới:

```http
GET /api/stocks/{symbol}/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Sau khi tích hợp, summary/report phải nhận được latest market, price history, BCTC, financial balance, VNINDEX/HoSE context, peer context, same-industry candidates, dataQuality và scoring định lượng thay vì để nhiều field `{}`/`null`.

## 2. Source code đã đọc

Đã đọc source trong `analyse`, gồm:

- `analyse/run.py`
- `analyse/README.md`
- `analyse/.env.example`
- `analyse/requirements.txt`
- `analyse/pyproject.toml`
- `analyse/src/analyse/main.py`
- `analyse/src/analyse/app.py`
- `analyse/src/analyse/config/settings.py`
- `analyse/src/analyse/api/routes.py`
- `analyse/src/analyse/api/dependencies.py`
- `analyse/src/analyse/clients/backend_client.py`
- `analyse/src/analyse/clients/http_client.py`
- `analyse/src/analyse/providers/*`
- `analyse/src/analyse/prompts/*`
- `analyse/src/analyse/research/*`
- `analyse/src/analyse/schemas/*`
- `analyse/src/analyse/services/*`
- `analyse/src/analyse/utils/*`
- `analyse/tests/*`
- `analyse/src/analyse/examples/*`

Không đọc `analyse/.env` thật để tránh lộ token/API key; dùng `.env.example` và `Settings` để kiểm tra cấu hình.

## 3. Vấn đề ban đầu

`analyse` vẫn đang dùng luồng cũ:

- `GET /api/watchlists`
- `GET /api/stocks/:symbol`
- `GET /api/stocks/:symbol/chart?range=3m`

Vì vậy report còn nhiều field rỗng/null:

- `financials_loaded=false`
- `bctc_3q.has_bctc=false`
- `bctc_3q.periods=[]`
- `financial_balance={}`
- `hose_market_context={}`
- `industry_peer_context={}`
- `market_general_context={}`
- `same_industry_recommendation={}`
- `scores.*=null`

## 4. Nguyên nhân gốc rễ

Nguyên nhân chính nằm ở phía `analyse`:

1. `BackendClient` chưa có method gọi `/analysis-data`.
2. `ReportService.analyse_one_report()` chưa ưu tiên endpoint mới.
3. `StockDataService` chỉ normalize detail/chart cũ, chưa map camelCase/snake_case từ contract mới.
4. `SummaryService` hard-code nhiều field `{}` và chỉ đọc `financials` theo kiểu cũ.
5. `ScoringService` là placeholder, trả `None` cho mọi điểm.
6. Markdown/HTML renderers chưa hiển thị peer/scoring/BCTC theo bảng đầy đủ.
7. Watchlist 401 tạo warning thô; chưa tách rõ watchlist optional và stock analysis-data.

## 5. Endpoint Backend mới đã tích hợp

Endpoint mới:

```http
GET /api/stocks/{symbol}/analysis-data
```

Query mặc định từ `.env`:

```env
exchange=HOSE
quarters=6
chartRange=3m
includePeers=true
includeMarketContext=true
```

Nếu endpoint này lỗi, service fallback sang:

```http
GET /api/stocks/{symbol}
GET /api/stocks/{symbol}/chart?range=3m
```

## 6. Thay đổi BackendClient

File: `analyse/src/analyse/clients/backend_client.py`

Đã thêm:

- `get_stock_analysis_data(...)`
- `_authorization_header()`
- Auth không lặp `Bearer` nếu `BACKEND_API_TOKEN` đã chứa `Bearer ...`
- Hỗ trợ `BACKEND_API_AUTH_SCHEME`
- `get_stock_chart()` hỗ trợ endpoint chart dạng `/api/stocks/{symbol}/chart` và gửi `range` qua query params

## 7. Thay đổi StockDataService

File: `analyse/src/analyse/services/stock_data_service.py`

Đã thêm `normalize_analysis_data()` để map:

- `latestMarket`/`latest_market`/`latest_price` -> `latest_market`
- `priceHistory`/`price_history` -> `price_history`
- `financials.periods` -> `financials.periods`
- `financialBalance`/`financial_balance` -> `financial_balance`
- `hoseMarketContext`/`market_overview` -> `hose_market_context`
- `industryPeerContext`/`industry_peer_context` -> `industry_peer_context`
- `marketGeneralContext`/`market_general_context` -> `market_general_context`
- `sameIndustryRecommendation`/`same_industry_recommendation` -> `same_industry_recommendation`
- `dataQuality` -> `data_quality` dạng snake_case ổn định

## 8. Thay đổi SummaryService mapping

File: `analyse/src/analyse/services/summary_service.py`

Đã viết lại mapping summary:

- `data_coverage.financials_loaded=true` khi có `financials.periods`
- `bctc_3q.periods` lấy 3 kỳ mới nhất, vẫn giữ `total_periods_available`
- `financial_balance` lấy từ `financialBalance`/`financial_balance`
- `hose_market_context`, `market_general_context`, `industry_peer_context`, `same_industry_recommendation` được map thật
- `dataQuality.missingFields` và `dataQuality.warnings` đi vào `data_quality_notes`/`warnings`
- `system_decision` dùng overall score, risk score, confidence, market regime và financials availability

## 9. Thay đổi ScoringService

File: `analyse/src/analyse/services/scoring_service.py`

Đã thay placeholder bằng scoring định lượng:

- `valuation_score`
- `quality_score`
- `growth_score`
- `momentum_score`
- `liquidity_score`
- `size_score`
- `risk_score`
- `risk_label`
- `overall_score`
- `overall_label`
- `score_confidence`
- `score_explanations`

Công thức dùng input từ Backend, không bịa số liệu. Nếu thiếu dữ liệu, service trả điểm partial trung tính và ghi giải thích.

## 10. Thay đổi Markdown/HTML report

Files:

- `analyse/src/analyse/services/markdown_service.py`
- `analyse/src/analyse/services/html_service.py`

Đã cập nhật để hiển thị:

- Bảng BCTC theo kỳ
- Financial balance
- Market context
- Peer comparison table
- Same-industry candidates
- Score dashboard có số
- Score explanations
- Data quality warnings

HTML vẫn escape dynamic text và không inject raw HTML từ LLM.

## 11. Xử lý `/api/watchlists` 401

`/api/watchlists` vẫn được gọi để hỗ trợ rule watchlist nếu có token. Nếu 401 và:

```env
BACKEND_WATCHLIST_REQUIRED=false
```

thì service không chặn phân tích, thêm warning:

```text
Không gọi được watchlists do thiếu/sai token. Phân tích vẫn tiếp tục bằng stock analysis-data.
```

Nếu `BACKEND_WATCHLIST_REQUIRED=true`, lỗi watchlist sẽ trả API error vì cấu hình yêu cầu watchlist là bắt buộc.

## 12. Xử lý external research adapters

File: `analyse/src/analyse/research/research_service.py`

Đã thêm `_build_adapters()` để adapter detection rõ ràng hơn:

- `ENABLE_VIETSTOCK=true` -> Vietstock adapter
- `ENABLE_CAFEF=true` -> CafeF adapter
- `ENABLE_GOOGLE_NEWS_RSS=true` và `RESEARCH_GOOGLE_NEWS_RSS_ENABLED=true` -> Google News RSS adapter

Nếu không adapter nào bật, response có warning rõ:

```text
Không có research adapter nào được bật.
```

Network/source failure vẫn không chặn report generation.

## 13. Cấu hình `.env.example` mới

Đã bổ sung:

```env
BACKEND_API_AUTH_SCHEME=Bearer
BACKEND_USE_ANALYSIS_DATA_ENDPOINT=true
BACKEND_ANALYSIS_DATA_ENDPOINT=/api/stocks/{symbol}/analysis-data
BACKEND_ANALYSIS_DATA_QUARTERS=6
BACKEND_ANALYSIS_DATA_CHART_RANGE=3m
BACKEND_ANALYSIS_DATA_INCLUDE_PEERS=true
BACKEND_ANALYSIS_DATA_INCLUDE_MARKET_CONTEXT=true
BACKEND_WATCHLIST_REQUIRED=false

ENABLE_SCORING=true
SCORING_MIN_FINANCIAL_PERIODS=3
SCORING_REQUIRE_FINANCIALS_FOR_OVERALL=false
SCORING_ENABLE_MARKET_CONTEXT=true
SCORING_ENABLE_PEER_CONTEXT=true
```

Đã kiểm tra mọi biến trong `.env.example` đều có field tương ứng trong `Settings`: không thiếu biến.

## 14. Files/classes/functions đã chỉnh

| File | Thay đổi | Lý do |
|---|---|---|
| `analyse/src/analyse/config/settings.py` | Thêm backend analysis-data, auth scheme, watchlist required, scoring flags, `PYTHONPATH` | Support đầy đủ `.env.example` |
| `analyse/.env.example` | Thêm biến Backend contract mới và scoring | Cấu hình mặc định dùng endpoint mới |
| `analyse/src/analyse/clients/backend_client.py` | Thêm `get_stock_analysis_data`, sửa auth header, sửa chart params | Gọi đúng Backend API mới |
| `analyse/src/analyse/services/stock_data_service.py` | Thêm `normalize_analysis_data` | Chuẩn hóa camelCase/snake_case contract |
| `analyse/src/analyse/services/report_service.py` | Ưu tiên analysis-data, fallback old endpoints, watchlist optional | Sửa luồng orchestration |
| `analyse/src/analyse/services/summary_service.py` | Viết lại mapping summary và system decision | Không còn hard-code field rỗng |
| `analyse/src/analyse/services/scoring_service.py` | Tính scoring định lượng | Không còn `scores.*=null` khi có dữ liệu |
| `analyse/src/analyse/services/markdown_service.py` | Thêm bảng BCTC/peer/candidates/scoring explanations | Báo cáo Markdown hiển thị dữ liệu mới |
| `analyse/src/analyse/services/html_service.py` | Thêm score cards, BCTC, peer table, dataQuality | Báo cáo HTML hiển thị dữ liệu mới |
| `analyse/src/analyse/research/research_service.py` | Thêm `_build_adapters` | Adapter detection rõ ràng |
| `analyse/README.md` | Cập nhật contract, env, Postman, troubleshooting | Tài liệu vận hành tiếng Việt |
| `analyse/tests/test_backend_client.py` | Test auth/query params/analysis-data | Khóa contract client |
| `analyse/tests/test_analyse_one_flow.py` | Fake Backend dùng analysis-data, test watchlist 401 optional | Kiểm tra flow end-to-end |
| `analyse/tests/test_summary_scoring.py` | Test mapping summary và scoring | Kiểm tra field không còn rỗng/null |
| `analyse/tests/test_report_renderers.py` | Test BCTC/peer/score trong Markdown/HTML | Kiểm tra renderer |
| `analyse/tests/test_external_research.py` | Test adapter detection/no adapter warning | Kiểm tra external research config |
| `analyse/tests/test_settings.py` | Test biến cấu hình mới | Đảm bảo Settings hỗ trợ `.env.example` |

## 15. Response trước và sau khi sửa

Trước:

```json
{
  "financials_loaded": false,
  "bctc_3q": { "has_bctc": false, "periods": [] },
  "financial_balance": {},
  "hose_market_context": {},
  "industry_peer_context": {},
  "scores": { "overall_score": null }
}
```

Sau, nếu Backend có dữ liệu:

```json
{
  "financials_loaded": true,
  "bctc_3q": { "has_bctc": true, "periods": [{ "period": "Q2/2026" }] },
  "financial_balance": { "total_assets": 500000 },
  "hose_market_context": { "vnindex": 1300.12 },
  "industry_peer_context": { "peers": [{ "symbol": "CMG" }] },
  "scores": {
    "valuation_score": 0,
    "quality_score": 0,
    "growth_score": 0,
    "momentum_score": 0,
    "liquidity_score": 0,
    "size_score": 0,
    "risk_score": 0,
    "overall_score": 0
  }
}
```

Các số score thực tế phụ thuộc dữ liệu Backend trả về.

## 16. Postman test đúng

Backend direct:

```http
GET http://localhost:5000/api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Analyse:

```http
POST http://localhost:5100/api/ai-reports/analyse-one
Content-Type: application/json
```

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
    "includeExternalResearch": false,
    "renderMarkdown": true,
    "renderHtml": true
  }
}
```

## 17. Test đã thêm/chạy

Đã thêm/chỉnh các test:

- BackendClient analysis-data query/auth
- Summary mapping analysis-data
- Scoring numeric/non-crash
- Report rendering BCTC/peer/score
- Watchlist 401 optional
- External research adapter config
- Settings `.env.example`

## 18. Kết quả test

Đã chạy:

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\analyse
python -m pytest
```

Kết quả:

```text
44 passed
```

## 19. Những phần cần kiểm tra thêm

- Cần kiểm tra thêm dữ liệu Mongo thật của Backend có đủ `financials.periods`, `hoseMarketContext`, `industryPeerContext.peers` hay không.
- Cần kiểm tra thêm đơn vị `market_cap` và các field tiền tệ BCTC vì phụ thuộc crawler/source Backend.
- External research cần internet và phụ thuộc Google News RSS/source public; nếu mạng lỗi hoặc nguồn không index bài, kết quả có thể rỗng.
- Nếu `BACKEND_API_TOKEN` hết hạn, `/api/watchlists` vẫn 401; cần login Backend và copy access token mới.

## 20. Kết luận

`analyse` đã được cập nhật để dùng Backend `analysis-data` làm nguồn chính, fallback sang endpoint cũ khi cần, map đầy đủ các field mới vào summary/report và tính scoring định lượng. Nếu Backend/Mongo có dữ liệu thật, report Markdown/HTML sẽ hiển thị BCTC, VNINDEX/HoSE context, peer comparison, same-industry candidates và dashboard điểm số thay vì các field rỗng/null.
