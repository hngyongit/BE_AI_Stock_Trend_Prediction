# Báo cáo kiểm tra API cho `analyse`: thiếu field/null nhiều

## 1. Mục tiêu kiểm tra

Mục tiêu là đọc source code trong `api`, xác định vì sao `analyse` nhận nhiều field rỗng/null khi gọi Backend API, tách rõ trách nhiệm giữa Backend API và `analyse`, sau đó bổ sung contract dữ liệu ổn định để `analyse` có thể lấy latest market, price history, BCTC, market context và peer context.

## 2. Source code đã đọc

Đã kiểm tra toàn bộ cấu trúc `api` recursively và đọc các nhóm file chính:

- `api/package.json`
- `api/README.md`
- `api/src/server.js`
- `api/src/app.js`
- `api/src/config/*`
- `api/src/common/middlewares/*`
- `api/src/common/utils/*`
- `api/src/database/models/*`
- `api/src/database/seeds/*`
- `api/src/modules/auth/*`
- `api/src/modules/watchlists/*`
- `api/src/modules/stocks/*`
- `api/src/modules/dashboard/*`
- `api/src/modules/users/*`
- `api/src/modules/subscriptions/*`
- `api/src/modules/admin-subscriptions/*`
- `api/src/modules/staff-subscriptions/*`
- Các module rỗng: `financials`, `market-overview`, `markets`, `industries`, `crawl-jobs`, `crawl-logs`, `data-sources`, `roles`
- `api/test-dashboard.js`

Trước khi chỉnh sửa, `api/.env.example` và thư mục `api/tests/*` không tồn tại: “Chưa thấy trong source code”. Sau chỉnh sửa đã tạo `api/.env.example` và test contract trong `api/test/test-api-analyse-contract.js`.

## 3. Response hiện tại từ `analyse`

Response hiện tại cho thấy:

- `/api/stocks/:symbol` gọi được và có latest price.
- `/api/stocks/:symbol/chart?range=3m` gọi được và có chart points.
- `/api/watchlists` trả `401 Unauthorized`.
- `financials_loaded=false`, `bctc_3q.has_bctc=false`, `financial_balance={}`.
- `hose_market_context={}`, `industry_peer_context={}`, `market_general_context={}`, `same_industry_recommendation={}`.
- `scores.*=null`.

## 4. Các field đang null/rỗng và nguyên nhân

| Field trong analyse | Nguồn kỳ vọng từ api | Hiện trạng api | Nguyên nhân | Cách sửa |
|---|---|---|---|---|
| `financials_loaded` | `factFinancialStatements` qua stock analysis endpoint | Trước sửa không expose | `/api/stocks/:symbol` chỉ trả profile/latest price | Đã thêm `GET /api/stocks/:symbol/analysis-data` và bổ sung `financials` vào detail cũ |
| `bctc_3q.periods` | 4-6 quý gần nhất | Trước sửa rỗng | Chưa có repository/service map BCTC | Đã map `net_revenue`, `profit_after_tax`, `total_assets`, `liabilities`, `equity`, v.v. sang `financials.periods` |
| `financial_balance` | Latest balance fields | API chưa trả field ổn định | Model có một số field tài sản/nợ nhưng endpoint cũ không expose | Đã trả `financialBalance`/`financial_balance`; `analyse` cần đọc key này thay vì chỉ đọc `financials` |
| `hose_market_context` | `factMarketOverviews` / VNINDEX | Trước sửa không expose qua `/api/stocks/:symbol` | Dashboard có đọc market overview nhưng endpoint stock không dùng | Đã trả `hoseMarketContext` và `market_overview` |
| `industry_peer_context` | `dimIndustries`, `dimStocks`, latest price, financials peer | Trước sửa không expose | Stock detail chỉ populate market, chưa populate industry/peer | Đã populate `industry_id`, thêm peer context |
| `market_general_context` | Market overview normalized | Trước sửa không có | Chưa có endpoint market overview công khai | Đã trả `marketGeneralContext`/`market_general_context` trong analysis payload |
| `same_industry_recommendation` | Ranking kỹ thuật từ peers | Trước sửa không có | Chưa có peer payload | Đã trả `sameIndustryRecommendation`; đây không phải khuyến nghị mua/bán cá nhân hóa |
| `scores.*` | `analyse.services.scoring_service` | API không tính | `ScoringService.build_placeholder_scores()` trả `None` | Thuộc `analyse`; API chỉ cung cấp input thô/chuẩn hóa |
| `/api/watchlists` 401 | Bearer JWT | Auth hoạt động đúng | `analyse` thiếu token hợp lệ hoặc token hết hạn/không hợp lệ | Gửi `Authorization: Bearer <access_token>` qua `BACKEND_API_TOKEN`; cần refresh token định kỳ |

## 5. Luồng `/api/watchlists` và nguyên nhân 401

`GET /api/watchlists` được khai báo trong `api/src/modules/watchlists/watchlists.routes.js`:

```js
router.get('/', authMiddleware, checkSubscriptionExpiry, watchlistsController.getWatchlist);
```

Middleware bảo vệ:

- `authMiddleware`: yêu cầu `Authorization: Bearer <access_token>`.
- `checkSubscriptionExpiry`: kiểm tra/downgrade plan nếu user PRO đã hết hạn.

Route này không dùng `roleMiddleware`, vì vậy mọi user `ACTIVE` với JWT hợp lệ đều truy cập được watchlist của chính mình. `401 Unauthorized` xảy ra khi thiếu header, sai format, token hết hạn, token ký sai secret, hoặc user không còn tồn tại.

## 6. Luồng `/api/stocks/:symbol`

Trước sửa, `getStockDetail()` chỉ gọi:

- `DimStock.findOne({ symbol })`
- `FactMarketPrice.findOne({ stock_id }).sort({ time_id: -1 })`

Nó không đọc BCTC, market overview hoặc peer data. Sau sửa, endpoint này vẫn giữ shape cũ nhưng bổ sung:

- `latestMarket`/`latest_market`
- `financials` dạng list để `analyse` hiện tại đọc được BCTC
- `financials_summary`
- `financialBalance`/`financial_balance`
- `market_overview`/`hoseMarketContext`
- `industryPeerContext`/`industry_peer_context`
- `marketGeneralContext`/`market_general_context`
- `sameIndustryRecommendation`/`same_industry_recommendation`
- `dataQuality`

## 7. Luồng `/api/stocks/:symbol/chart`

Endpoint này đã hoạt động trước khi sửa. Nó đọc `FactMarketPrice` theo `range` và trả list OHLCV:

```json
[
  { "time": "2026-06-19", "open": 71600, "high": 71800, "low": 70800, "close": 71500, "volume": 14295100 }
]
```

Sau sửa, logic range dùng chung helper `getRangeLimit()` để endpoint chart và analysis-data nhất quán.

## 8. Dữ liệu BCTC/financials trong MongoDB/API

Model có sẵn:

- `FactFinancialStatement` / collection `factFinancialStatements`
- `FactFinancialReportSource` / collection `factFinancialReportSources`
- `DimReportPeriod` / collection `dimReportPeriods`
- `DimStockDataSource` / collection `dimStockDataSources`

Trước sửa, module `api/src/modules/financials/*` rỗng và không có endpoint expose BCTC: “Chưa thấy trong source code”.

Sau sửa, `stocks.repository.findFinancialStatementsForStock()` đọc `factFinancialStatements`, populate `report_period_id` và `data_source_id`, sort theo năm/quý giảm dần và map sang contract:

- `period`, `year`, `quarter`
- `revenue`, `gross_profit`, `operating_profit`
- `profit_before_tax`, `profit_after_tax`, `parent_profit`
- `eps`
- `total_assets`, `total_liabilities`, `equity`
- `current_assets`, `current_liabilities`
- một số field ngân hàng nếu có

Các field cash-flow như `cash`, `debt`, `operating_cash_flow`, `free_cash_flow` chưa có model rõ ràng nên trả `null`: “Chưa thấy trong source code”.

## 9. Dữ liệu HOSE/VNINDEX/market context

Model có sẵn `FactMarketOverview` / collection `factMarketOverviews`.

Trước sửa, chỉ dashboard repository đọc market overview, không có endpoint stock-level cho `analyse`. Sau sửa, stock analysis payload đọc latest overview theo market, ưu tiên symbol `VNINDEX` cho HOSE, rồi map:

- `vnindex`
- `change`
- `change_percent`
- `total_volume`
- `total_value`
- `foreign_net`
- `regime`
- `regime_score`
- `updated_at`

Breadth `advancers/decliners/unchanged` chưa có trong model nên trả `null`: “Chưa thấy trong source code”.

## 10. Dữ liệu ngành/peer

Model có sẵn:

- `DimIndustry`
- `DimStock.industry_id`
- `FactMarketPrice`
- `FactFinancialStatement`

Trước sửa, `findStockBySymbol()` chỉ populate `market_id`, chưa populate `industry_id`; không có peer query. Sau sửa:

- `findStockBySymbol()` populate thêm `industry_id`.
- `findPeersByIndustry()` tìm các mã ACTIVE cùng ngành.
- Service map peer sang `symbol`, `company`, `exchange`, `close_price`, `pe`, `pb`, `roe`, `market_cap`, `profit_after_tax`, `revenue`, `momentum_1m`.

Nếu stock chưa có `industry_id` hoặc không có mã cùng ngành, `dataQuality.missingFields` sẽ ghi rõ.

## 11. Contract API đề xuất cho `analyse`

Endpoint mới:

```http
GET /api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Response nằm trong `data`:

```json
{
  "symbol": "FPT",
  "exchange": "HOSE",
  "company": "CTCP FPT",
  "latestMarket": {},
  "latest_market": {},
  "priceHistory": [],
  "price_history": [],
  "financials": { "periods": [] },
  "financialBalance": {},
  "financial_balance": {},
  "hoseMarketContext": {},
  "market_overview": {},
  "industryPeerContext": { "industry": {}, "peers": [] },
  "industry_peer_context": { "industry": {}, "peers": [] },
  "marketGeneralContext": {},
  "market_general_context": {},
  "sameIndustryRecommendation": {},
  "same_industry_recommendation": {},
  "dataQuality": {
    "financialsLoaded": true,
    "financialPeriodsCount": 6,
    "priceHistoryPoints": 24,
    "marketContextLoaded": true,
    "peerContextLoaded": true,
    "missingFields": [],
    "warnings": []
  }
}
```

## 12. Thay đổi đã thực hiện

| File | Thay đổi | Lý do |
|---|---|---|
| `api/src/modules/stocks/stocks.repository.js` | Thêm query BCTC, market overview, peer; populate `industry_id` | Lấy đủ source data từ Mongo |
| `api/src/modules/stocks/stocks.service.js` | Thêm mapper latest market, price history, financial periods, balance, market context, peers, dataQuality; thêm `getStockAnalysisData()` | Chuẩn hóa contract cho `analyse` |
| `api/src/modules/stocks/stocks.controller.js` | Thêm `getStockAnalysisData()` | Expose service qua HTTP |
| `api/src/modules/stocks/stocks.routes.js` | Thêm `GET /:symbol/analysis-data` | Endpoint riêng cho analyse |
| `api/src/modules/stocks/stocks.validation.js` | Thêm validation query cho endpoint mới | Chặn query sai kiểu |
| `api/package.json` | Cập nhật `npm test` chạy contract test hiện có | Script cũ trỏ tới test file không tồn tại |
| `api/test/test-api-analyse-contract.js` | Tạo test auth watchlist và contract stocks | Kiểm tra fix không cần Mongo thật |
| `api/.env.example` | Tạo file mẫu env | Trước đó chưa thấy trong source code |
| `api/README.md` | Viết hướng dẫn contract, auth, Postman, Mongo diagnostics, test | Documentation tiếng Việt cho tích hợp analyse |

## 13. Endpoint mới hoặc endpoint đã mở rộng

Endpoint mới:

```http
GET /api/stocks/:symbol/analysis-data
```

Query:

- `exchange`: ví dụ `HOSE`
- `quarters`: 1-12, mặc định 6
- `chartRange`: `7d`, `1m`, `3m`, `6m`, `1y`, `all`
- `includePeers`: boolean
- `includeMarketContext`: boolean

Endpoint mở rộng backward-compatible:

```http
GET /api/stocks/:symbol
```

Endpoint này vẫn trả các field cũ, đồng thời bổ sung field mới để `analyse` hiện tại có thể nhận `financials` list và `market_overview`.

## 14. Auth/token cần dùng

Watchlist:

```http
Authorization: Bearer <access_token>
```

Lấy token:

```http
POST /api/auth/login
```

Seed user local:

- `admin@example.com` / `admin123456`
- `user@example.com` / `user123456`
- `staff@example.com` / `staff123456`

Không thêm service-token cho watchlist vì watchlist là dữ liệu cá nhân theo user. Cách an toàn hiện tại là dùng JWT user hợp lệ.

## 15. Cách test bằng Postman

Login:

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

Watchlists:

```http
GET http://localhost:5000/api/watchlists
Authorization: Bearer <access_token>
```

Stock detail:

```http
GET http://localhost:5000/api/stocks/FPT
```

Stock analysis data:

```http
GET http://localhost:5000/api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

## 16. Test đã thêm/chạy

Đã thêm `api/test/test-api-analyse-contract.js`, gồm:

- `/api/watchlists` không token trả 401.
- `/api/watchlists` có Bearer JWT hợp lệ trả 200.
- `stocksService.getStockAnalysisData()` trả `latestMarket`, `financials.periods`, `priceHistory`, `dataQuality`.
- Mapping không expose raw field như `net_revenue` trong financial period.
- Thiếu BCTC/market/peer vẫn trả response có `dataQuality.warnings`.
- `getStockDetail()` có field bổ sung backward-compatible cho `analyse`.

## 17. Kết quả test

Đã chạy:

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\api
npm test
```

Kết quả:

```text
All 4 api analyse contract tests passed.
```

## 18. Những phần vẫn cần kiểm tra thêm

- Cần kiểm tra thêm dữ liệu thật trong MongoDB production/local có đủ `factFinancialStatements`, `factMarketOverviews`, `industry_id` hay không.
- Cần kiểm tra thêm đơn vị của `market_cap`, doanh thu/lợi nhuận/tài sản trong BCTC vì model chưa ghi metadata đơn vị.
- Cần kiểm tra thêm crawler/importer thực tế vì các module `crawl-jobs`, `crawl-logs`, `data-sources`, `financials`, `market-overview`, `industries` đang rỗng trong source code.
- `analyse` cần cập nhật mapper nếu muốn dùng trực tiếp `financial_balance`, `industry_peer_context`, `market_general_context`, `same_industry_recommendation` từ payload mới. Hiện `SummaryService` vẫn hard-code một số field là `{}`.
- `scores.*` vẫn thuộc `analyse.services.scoring_service`; API không nên tính score đầu tư.

## 19. Kết luận

Nguyên nhân gốc rễ là Backend API đã có một số model Mongo cho financials, market overview và industry, nhưng endpoint stock cũ không đọc/expose các collection đó. `/api/watchlists` trả 401 là hành vi auth đúng vì route yêu cầu Bearer JWT. Các score null là do `analyse` đang dùng scoring placeholder, không phải do API trực tiếp.

Đã bổ sung endpoint `GET /api/stocks/:symbol/analysis-data`, mở rộng `GET /api/stocks/:symbol` theo hướng backward-compatible, thêm `dataQuality`, tài liệu tiếng Việt và test contract. Phần còn lại cần làm ở `analyse` là map các key mới và triển khai scoring định lượng từ dữ liệu API cung cấp.
