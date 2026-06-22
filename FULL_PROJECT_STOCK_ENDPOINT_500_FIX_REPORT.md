# Báo cáo sửa lỗi stock endpoint 500 và coverage sai

## 1. Mục tiêu

Sửa lỗi các stock endpoint Backend trả `500 Internal Server Error`, đồng thời sửa logic `analyse` đang đánh dấu dữ liệu Backend là loaded dù các call `/analysis-data`, `/stocks/:symbol`, `/chart` thất bại.

Public request của `analyse` được giữ nguyên, không đổi field request/response public.

## 2. Source code đã đọc

Đã kiểm tra toàn bộ cây source hiện có theo các nhóm:

- Root: `README.md`, `PROJECT_DOCUMENTATION.md`, `.gitignore`. Chưa thấy trong source code: root `package.json`, root `.env.example`, Docker/deployment file.
- `api`: `package.json`, `.env.example`, `README.md`, `src/app.js`, `src/server.js`, `src/config/*`, `src/common/*`, `src/database/models/*`, `src/database/seeds/*`, các module `auth`, `watchlists`, `stocks`, `dashboard`, `financials`, `market-overview`, `markets`, `industries`, `crawl-jobs`, `crawl-logs`, `data-sources`, `users`, `subscriptions`, test.
- `analyse`: `run.py`, `README.md`, `.env.example`, `pyproject.toml`, `requirements.txt`, `src/analyse/config`, `api`, `clients`, `providers`, `prompts`, `research`, `schemas`, `services`, `utils`, `tests`, `examples`.
- `crawler`: README, config, MongoDB service, market overview job/model, parsers/utils chính. Cần kiểm tra thêm nếu muốn audit đầy đủ pipeline crawl thực tế trong môi trường deploy.
- Chưa thấy trong source code: thư mục `backend` và `frontend` riêng biệt.

## 3. Lỗi hiện tại

Production Backend:

```http
GET https://lobster-app-kte4b.ondigitalocean.app/api/stocks/FPT
GET https://lobster-app-kte4b.ondigitalocean.app/api/stocks/FPT/chart?range=3m
GET https://lobster-app-kte4b.ondigitalocean.app/api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

đều trả `500`.

Body lỗi production cho thấy:

```text
Schema hasn't been registered for model "DimIndustry".
Use mongoose.model(name, schema)
```

Trong `analyse`, dù Backend trả 500, coverage vẫn có lúc hiện:

```json
{
  "backend_stock_detail_loaded": true,
  "analysis_data_loaded": true
}
```

Đây là sai vì service đang nhìn vào object placeholder/raw thay vì trạng thái call Backend thật.

## 4. Nguyên nhân gốc rễ

1. Backend crash vì `api/src/modules/stocks/stocks.repository.js` gọi `populate('industry_id')` trên `DimStock`, trong khi model `DimIndustry` chưa được require/register trước khi query chạy ở production.
2. Các phần dữ liệu optional trong `stocks.service.js` được gom bằng `Promise.all`. Nếu financials, market overview, peer hoặc chart helper lỗi, toàn bộ endpoint có thể rơi 500.
3. `analyse` fallback tạo object placeholder có `symbol`, rồi `SummaryService` suy ra loaded bằng `bool(stock_detail)` và `bool(raw)`, khiến flag coverage bị true dù Backend call failed.
4. External research chưa lọc tốt tuổi bài và dễ lẫn bài FPT Retail/FRT khi phân tích mã FPT mẹ.

## 5. Backend endpoints bị ảnh hưởng

- `GET /api/stocks/:symbol`
- `GET /api/stocks/:symbol/chart?range=3m`
- `GET /api/stocks/:symbol/analysis-data?...`

Các endpoint cũ vẫn được giữ backward-compatible.

## 6. Thay đổi trong `api`

- Đăng ký model Mongoose cần cho populate: `DimMarket`, `DimIndustry`, `DimReportPeriod`, `DimStockDataSource`.
- Chuẩn hóa symbol bằng `trim().toUpperCase()` trước khi query.
- Bọc các truy vấn optional bằng `safeOptionalRead`: lỗi optional data trả object/array rỗng và warning trong `dataQuality`, không kéo endpoint xuống 500.
- `getStockDetail()` không còn gọi latest price rời rạc dễ crash; dùng payload đã chuẩn hóa từ `buildAnalysisDataForStock`.
- `getStockChart()` trả `[]` nếu chart query optional lỗi sau khi stock đã tồn tại.
- Controller stock ghi log lỗi 500 an toàn gồm endpoint, symbol, query, error name/message và stack ở non-production.

## 7. Thay đổi trong `analyse`

- `ReportService._load_stock_detail_for_analysis()` gắn metadata nội bộ `_source_success`:
  - `analysis_data_loaded`
  - `backend_stock_detail_loaded`
  - `chart_loaded`
- `StockDataService.normalize_analysis_data()` giữ metadata này khi chuẩn hóa.
- `SummaryService.build_summary()` tính coverage từ `_source_success` và dữ liệu thực sự có ích, không từ placeholder.
- Nếu `/analysis-data` fail, fallback sang endpoint cũ; nếu endpoint cũ cũng fail, report vẫn tạo được nhưng coverage false/0 và warnings rõ ràng.
- Watchlist 401 được giữ optional khi `BACKEND_WATCHLIST_REQUIRED=false` và chỉ thêm một warning rõ.
- Deduplicate warnings ở các điểm merge chính.

## 8. Contract public được giữ nguyên

Không đổi public request body của:

```http
POST /api/ai-reports/analyse-one
```

Không đổi tên field response hiện có như `data_sources`, `summary`, `data_coverage`, `latest_market`, `bctc_3q`, `markdown_report`, `html_report`.

## 9. Request public giữ nguyên

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

## 10. API nội bộ được gọi

`analyse` vẫn ưu tiên:

```http
GET /api/stocks/:symbol/analysis-data
```

Sau đó fallback:

```http
GET /api/stocks/:symbol
GET /api/stocks/:symbol/chart?range=3m
GET /api/watchlists
```

`/api/watchlists` vẫn yêu cầu `Authorization: Bearer <access_token>` nếu cần dùng watchlist.

## 11. Mapping data coverage trước/sau

| Field | Trước | Sau | Lý do |
| ----- | ----- | --- | ----- |
| `analysis_data_loaded` | Có thể true nếu có raw/placeholder | True chỉ khi `/analysis-data` trả payload dùng được | Không đánh dấu loaded khi Backend 500 |
| `backend_stock_detail_loaded` | Có thể true nếu có placeholder | True chỉ khi `/api/stocks/:symbol` trả payload dùng được | Placeholder không còn được xem là dữ liệu Backend |
| `latest_price_loaded` | True nếu `latest_market` là dict bất kỳ | True khi có field giá/volume | Object rỗng không phải dữ liệu giá |
| `financials_loaded` | Dựa trên periods | Giữ dựa trên `financials.periods.length > 0` | Đúng contract |
| `price_history_points` | Có thể bị giữ từ placeholder | Bằng đúng length `price_history` | Chart fail thì bằng 0 |
| `market_context_loaded` | True nếu context là dict bất kỳ | True khi có VNINDEX/change/regime/volume | Object rỗng không còn bị loaded |
| `peer_context_loaded` | True nếu peers không rỗng | Giữ dựa trên peers length | Đúng contract |

## 12. Xử lý missing optional data

Backend không fake dữ liệu. Khi stock tồn tại nhưng thiếu optional data:

- `financials.periods=[]`
- `priceHistory=[]`
- `hoseMarketContext={}`
- `industryPeerContext.peers=[]`
- `sameIndustryRecommendation={}`
- `dataQuality.warnings` ghi nguyên nhân

Nếu symbol không tồn tại, API trả lỗi chuẩn 404.

## 13. Xử lý watchlist 401

`/api/watchlists` vẫn được bảo vệ bởi auth middleware. Khi `analyse` không có token hoặc token sai:

```text
Không gọi được watchlists do thiếu/sai token. Phân tích vẫn tiếp tục bằng dữ liệu cổ phiếu.
```

Nếu `BACKEND_WATCHLIST_REQUIRED=false`, lỗi này không chặn report.

## 14. Xử lý external research

- Thêm cấu hình `RESEARCH_MAX_ARTICLE_AGE_DAYS=730`.
- Google News RSS bỏ qua bài quá tuổi cấu hình.
- Khi phân tích `FPT`, loại bài chỉ nói về FPT Retail/FRT nếu nội dung không thể hiện rõ chủ đề là công ty mẹ FPT.
- Dedupe flags và dedupe bài theo tiêu đề chuẩn hóa.
- Sắp xếp ưu tiên bài mới hơn, sau đó relevance/source priority.

## 15. Files/classes/functions đã chỉnh

| File | Thay đổi | Lý do |
| ---- | -------- | ----- |
| `api/src/modules/stocks/stocks.repository.js` | Require/register model populate, chuẩn hóa symbol | Sửa root cause `DimIndustry` MissingSchemaError và hỗ trợ `fpt`, ` FPT ` |
| `api/src/modules/stocks/stocks.service.js` | Thêm `safeOptionalRead`, optional warnings, chart safe fallback, dataQuality dedupe | Optional data thiếu/lỗi không gây 500 |
| `api/src/modules/stocks/stocks.controller.js` | Thêm `logStockEndpointError` | Debug production 500 an toàn |
| `api/test/test-api-analyse-contract.js` | Thêm test route stock, optional query lỗi, 404 | Chống regression endpoint stock |
| `api/README.md` | Document stock endpoints, 500 diagnosis, optional data behavior | Hướng dẫn vận hành/debug |
| `analyse/src/analyse/services/report_service.py` | Gắn `_source_success`, sửa fallback status, dedupe warnings, watchlist warning | Coverage phản ánh Backend success/fail thật |
| `analyse/src/analyse/services/stock_data_service.py` | Preserve `_source_success` khi normalize | Truyền metadata nội bộ sang summary |
| `analyse/src/analyse/services/summary_service.py` | Coverage dựa trên source status và dữ liệu hữu ích | Sửa `analysis_data_loaded/backend_stock_detail_loaded` sai |
| `analyse/src/analyse/config/settings.py` | Thêm `RESEARCH_MAX_ARTICLE_AGE_DAYS` | Cấu hình lọc tuổi bài |
| `analyse/.env.example` | Thêm `RESEARCH_MAX_ARTICLE_AGE_DAYS=730` | Đồng bộ env |
| `analyse/src/analyse/research/google_news.py` | Lọc bài cũ, lọc FPT Retail/FRT, dedupe flags/title, sort mới hơn | Tăng relevance external research |
| `analyse/src/analyse/research/research_service.py` | Dedupe title, sort theo recency/relevance/source | Giảm tin trùng/cũ |
| `analyse/tests/test_analyse_one_flow.py` | Test Backend 500 coverage false và report vẫn sinh | Chống regression fallback |
| `analyse/tests/test_external_research.py` | Test lọc bài cũ và FPT Retail | Chống regression research relevance |
| `analyse/README.md` | Document coverage flags, fallback, research age/FPT Retail filter | Hướng dẫn vận hành |

## 16. Test đã thêm/chạy

API:

- Watchlist không token 401, token hợp lệ 200.
- Stock analysis-data contract đầy đủ.
- Stock detail backward-compatible.
- Thiếu BCTC/market/peer không crash.
- Route `/api/stocks/FPT`, `/chart`, `/analysis-data` trả 200 khi stock tồn tại.
- Optional financial/market/peer/chart query lỗi vẫn không trả 500.
- Invalid symbol trả 404.

Analyse:

- Backend stock APIs trả 500 thì coverage flags false/0.
- Report vẫn tạo Markdown/HTML khi thiếu Backend data.
- Warnings deduplicate.
- Research bỏ bài cũ và bài FPT Retail/FRT không phù hợp.

## 17. Kết quả test

Đã chạy:

```powershell
cd api
npm test
```

Kết quả: `All 7 api analyse contract tests passed.`

Đã chạy:

```powershell
cd analyse
python -m pytest
```

Kết quả: `46 passed`.

Trong test API có log chủ động cho case negative: chart collection lỗi và 404 invalid symbol. Đây là dữ liệu test, không phải test fail.

## 18. Manual curl/Postman checks

Đã kiểm tra production trước redeploy:

```bash
curl "https://lobster-app-kte4b.ondigitalocean.app/api/stocks/FPT"
curl "https://lobster-app-kte4b.ondigitalocean.app/api/stocks/FPT/chart?range=3m"
curl "https://lobster-app-kte4b.ondigitalocean.app/api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true"
```

Kết quả hiện tại production: vẫn `500`, body là `MissingSchemaError` cho `DimIndustry`. Cần redeploy `api` sau khi merge bản sửa để production hết lỗi.

Sau deploy, kỳ vọng:

- `/api/stocks/FPT` không còn 500 nếu stock tồn tại.
- `/api/stocks/FPT/chart?range=3m` trả 200 với array, có thể rỗng.
- `/api/stocks/FPT/analysis-data?...` trả 200 với payload chuẩn hóa, optional data rỗng kèm warning nếu Mongo thiếu record.

## 19. Những phần cần kiểm tra thêm

- Cần kiểm tra thêm dữ liệu thật trong MongoDB production: `dimStocks`, `factMarketPrices`, `factFinancialStatements`, `factMarketOverviews`, `dimIndustries`.
- Cần kiểm tra thêm deploy pipeline vì chưa thấy Docker/deployment file trong source code.
- Nếu production vẫn thiếu BCTC sau khi endpoint hết 500, nguyên nhân có thể là MongoDB chưa có `factFinancialStatements` cho mã đó, không phải lỗi `analyse`.
- Nếu market context rỗng, kiểm tra crawler/upsert `factMarketOverviews`.

## 20. Kết luận

Root cause 500 đã xác định cụ thể: thiếu đăng ký Mongoose model `DimIndustry` trước khi populate. Code Backend đã được sửa để đăng ký model và để optional data thiếu/lỗi không làm sập stock endpoints. `analyse` đã được sửa để coverage flags phản ánh đúng trạng thái Backend call thật, không còn đánh dấu loaded khi `/analysis-data`, `/stocks/:symbol`, `/chart` trả 500.

Production URL cần redeploy bản `api` mới để hết 500.
