# API service cho AI Stock Trend Prediction

## Contract dữ liệu cho `analyse`

Service `analyse` cần API cung cấp dữ liệu thô/chuẩn hóa, còn việc tính điểm đầu tư vẫn thuộc `analyse`.

Endpoint khuyến nghị:

```http
GET /api/stocks/:symbol/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Response nằm trong `data` và có các nhóm chính:

```json
{
  "symbol": "FPT",
  "exchange": "HOSE",
  "company": "CTCP FPT",
  "latestMarket": {},
  "priceHistory": [],
  "financials": { "periods": [] },
  "financialBalance": {},
  "hoseMarketContext": {},
  "industryPeerContext": { "industry": {}, "peers": [] },
  "marketGeneralContext": {},
  "sameIndustryRecommendation": {},
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

Endpoint cũ `GET /api/stocks/:symbol` vẫn giữ shape cũ và được bổ sung field backward-compatible như `financials`, `financial_balance`, `market_overview`, `industryPeerContext` để `analyse` hiện tại không bị rỗng hoàn toàn.

## Endpoint cần dùng

- `GET /api/stocks/:symbol`: profile, latest price và field bổ sung cho analyse hiện tại.
- `GET /api/stocks/:symbol/chart?range=3m`: lịch sử giá OHLCV.
- `GET /api/stocks/:symbol/analysis-data?...`: payload chuẩn hóa đầy đủ cho analyse.
- `GET /api/watchlists`: watchlist cá nhân, bắt buộc Bearer JWT.
- `POST /api/auth/login`: lấy access token/refresh token.

## Stock endpoints và lỗi 500

Các route stock phải trả 200 khi mã tồn tại, kể cả khi dữ liệu phụ chưa có:

```http
GET /api/stocks/FPT
GET /api/stocks/FPT/chart?range=3m
GET /api/stocks/FPT/analysis-data?exchange=HOSE&quarters=6&chartRange=3m&includePeers=true&includeMarketContext=true
```

Nếu stock tồn tại nhưng thiếu BCTC, market overview, peer hoặc chart, API trả object/array rỗng kèm `dataQuality.warnings`, không trả 500. Nếu symbol không tồn tại, API trả lỗi chuẩn 404.

Lỗi production từng gặp:

```text
Schema hasn't been registered for model "DimIndustry".
```

Nguyên nhân là `DimStock.industry_id` có `ref: "DimIndustry"` nhưng model chưa được require trước khi `populate("industry_id")`. Module stock repository hiện đăng ký sẵn `DimMarket`, `DimIndustry`, `DimReportPeriod` và `DimStockDataSource` trước khi chạy populate.

Khi endpoint stock vẫn trả 500, kiểm tra log server. Controller stock ghi log an toàn gồm endpoint, symbol, query, error name/message và stack ở môi trường non-production.

## Behavior khi thiếu optional data

`analysis-data` luôn cố dựng payload ổn định:

```json
{
  "latestMarket": {},
  "priceHistory": [],
  "financials": { "periods": [] },
  "financialBalance": {},
  "hoseMarketContext": {},
  "industryPeerContext": { "industry": {}, "peers": [] },
  "marketGeneralContext": {},
  "sameIndustryRecommendation": {},
  "dataQuality": {
    "missingFields": [],
    "warnings": []
  }
}
```

Các phần BCTC/market/peer là optional. Không fake dữ liệu: nếu MongoDB chưa có record thì field để rỗng và ghi warning.

## Auth/token

`/api/watchlists` dùng middleware `authMiddleware`, yêu cầu header:

```http
Authorization: Bearer <access_token>
```

Mọi user `ACTIVE` đăng nhập hợp lệ đều truy cập được watchlist của chính mình. Route này không dùng role middleware, nhưng vẫn chạy `checkSubscriptionExpiry`.

Seed local tạo sẵn:

- `user@example.com` / `user123456`
- `staff@example.com` / `staff123456`
- `admin@example.com` / `admin123456`

Access token mặc định hết hạn theo `JWT_ACCESS_EXPIRES_IN` trong `.env`.

## Test bằng Postman

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

## Kiểm tra MongoDB khi thiếu field

Các collection/model API đang đọc:

- `dimStocks`: mã, công ty, sàn, ngành.
- `factMarketPrices`: latest market data và chart/price history.
- `factFinancialStatements`: BCTC đã chuẩn hóa.
- `factMarketOverviews`: VNINDEX/market overview.
- `dimIndustries`: ngành/sector để dựng peer.
- `watchlists`: watchlist theo user.

Ví dụ kiểm tra bằng Mongo shell:

```javascript
db.dimStocks.findOne({ symbol: "FPT" })
db.factMarketPrices.find({ stock_id: ObjectId("<stock_id>") }).sort({ time_id: -1 }).limit(3)
db.factFinancialStatements.find({ stock_id: ObjectId("<stock_id>") }).limit(6)
db.factMarketOverviews.find({ symbol: "VNINDEX" }).sort({ time_id: -1 }).limit(1)
```

Nếu `financials.periods` rỗng, kiểm tra `factFinancialStatements`. Nếu `hoseMarketContext` rỗng, kiểm tra `factMarketOverviews`. Nếu `industryPeerContext.peers` rỗng, kiểm tra `industry_id` của stock và các mã cùng `industry_id`.

## Chạy test

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\api
npm test
```

Test hiện kiểm tra auth watchlist, contract `analysis-data`, mapping field BCTC/market/peer, và behavior khi thiếu dữ liệu.
