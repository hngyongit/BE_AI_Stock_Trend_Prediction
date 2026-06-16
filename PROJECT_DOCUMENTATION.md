# Tài liệu dự án

## 1. Tổng quan dự án

Dự án `BE_AI_Stock_Trend_Prediction` là backend cho hệ thống thu thập, lưu trữ và cung cấp dữ liệu chứng khoán Việt Nam, tập trung vào dữ liệu từ Vietstock và MongoDB.

Source code hiện có hai phần chính:

- `api`: dịch vụ REST API viết bằng Node.js, Express và Mongoose. API xử lý xác thực, người dùng, cổ phiếu, watchlist, dashboard và subscription qua PayOS.
- `crawler`: dịch vụ/script Python dùng Playwright, requests, BeautifulSoup, PyMongo và Google Sheets để crawl dữ liệu Vietstock, ghi dữ liệu vào MongoDB và tùy chọn ghi Google Sheets.

Theo source code hiện tại, phần dự đoán AI/ML chưa được triển khai. Có `LLMService` trong crawler nhưng mới là hook mở rộng, chưa gọi nhà cung cấp LLM thật.

Một số nội dung trong `README.md` gốc mô tả các module đang phát triển, nhưng source hiện tại có nhiều file module API đang để trống 0 byte. Tài liệu này ưu tiên trạng thái thực tế trong source code.

## 2. Cấu trúc thư mục

```text
BE_AI_Stock_Trend_Prediction/
├── README.md
├── PROJECT_DOCUMENTATION.md
├── .gitignore
├── api/
│   ├── package.json
│   ├── package-lock.json
│   ├── README.md
│   ├── README-GOOGLE-OAUTH.md
│   ├── test-dashboard.js
│   └── src/
│       ├── app.js
│       ├── server.js
│       ├── config/
│       │   ├── app.config.js
│       │   ├── database.config.js
│       │   ├── env.config.js
│       │   ├── jwt.config.js
│       │   ├── passport.config.js
│       │   ├── plan.config.js
│       │   └── swagger.config.js
│       ├── common/
│       │   ├── middlewares/
│       │   │   ├── auth.middleware.js
│       │   │   ├── error.middleware.js
│       │   │   ├── role.middleware.js
│       │   │   └── subscription.middleware.js
│       │   ├── stores/
│       │   │   └── oauth-exchange.store.js
│       │   └── utils/
│       │       ├── jwt.util.js
│       │       └── response.util.js
│       ├── database/
│       │   ├── models/
│       │   ├── seeds/
│       │   └── indexes/
│       └── modules/
│           ├── auth/
│           ├── users/
│           ├── stocks/
│           ├── watchlists/
│           ├── dashboard/
│           ├── subscriptions/
│           ├── roles/
│           ├── markets/
│           ├── industries/
│           ├── data-sources/
│           ├── financials/
│           ├── crawl-jobs/
│           ├── crawl-logs/
│           └── market-overview/
└── crawler/
    ├── README.md
    ├── requirements.txt
    ├── pyproject.toml
    ├── run.py
    ├── inspect_db.py
    ├── manual_crawl_by_date_improved.py
    ├── docs/
    │   ├── ARCHITECTURE.md
    │   ├── CONFIGURATION.md
    │   └── GOOGLE_SHEETS_SETUP.md
    ├── scripts/
    │   ├── market_overview_crawler.py
    │   └── init_market_overviews_from_json.py
    ├── src/
    │   └── vietstock_crawler/
    │       ├── app.py
    │       ├── config/
    │       ├── core/
    │       ├── jobs/
    │       ├── models/
    │       ├── parsers/
    │       ├── services/
    │       └── utils/
    └── tests/
```

Các file quan trọng:

- `api/src/server.js`: entry point của API, kết nối MongoDB, seed role/user mặc định và start Express server.
- `api/src/app.js`: cấu hình middleware, Swagger và mount các route thật sự đang hoạt động.
- `api/src/config/env.config.js`: danh sách biến môi trường của API.
- `api/src/database/models/*.js`: schema Mongoose cho MongoDB.
- `crawler/run.py`: entry point gọi `vietstock_crawler.app.run`.
- `crawler/src/vietstock_crawler/app.py`: orchestration chính của crawler, nhưng hiện có lỗi cú pháp tại dòng `elif result["status"] == "SKIPPED"` trong source hiện tại.
- `crawler/manual_crawl_by_date_improved.py`: script crawl thủ công theo ngày, có provider fallback, nhưng hiện có rủi ro lỗi runtime do biến chưa khởi tạo trong `main()`.
- `crawler/scripts/market_overview_crawler.py`: script crawl dữ liệu KQGD/market overview bằng Playwright.
- `crawler/src/vietstock_crawler/services/mongodb_service.py`: ghi dữ liệu crawler vào MongoDB bằng PyMongo.
- `crawler/src/vietstock_crawler/services/google_sheets_service.py`: đọc/ghi Google Sheets.

## 3. Công nghệ sử dụng

API:

- Node.js, phiên bản yêu cầu: Chưa xác định rõ trong source code vì `api/package.json` không có trường `engines`.
- Express `^4.19.2`.
- MongoDB với Mongoose `^8.4.1`.
- JWT bằng `jsonwebtoken`.
- Hash password bằng `bcryptjs`.
- Google OAuth bằng `passport`, `passport-google-oauth20`, `express-session`.
- Security/logging middleware: `helmet`, `cors`, `morgan`.
- Validation bằng `express-validator`.
- Swagger/OpenAPI bằng `swagger-jsdoc`, `swagger-ui-express`.
- PayOS bằng `@payos/node`.
- Dev server bằng `nodemon`.

Crawler:

- Python yêu cầu `>=3.11` theo `crawler/pyproject.toml`. `.venv/pyvenv.cfg` hiện cho thấy môi trường local từng dùng Python `3.13.7`.
- Playwright để mở trang Vietstock.
- requests để fallback HTTP trực tiếp và gọi provider API.
- BeautifulSoup4 và lxml để parse HTML.
- pandas cho xử lý giá trị rỗng/NaN.
- PyMongo và dnspython để kết nối MongoDB.
- gspread và google-auth để đọc/ghi Google Sheets.
- python-dotenv để đọc `.env`.
- pytest cho test.

External service/source:

- Vietstock Finance: `https://finance.vietstock.vn`.
- Google Sheets/Google Drive API.
- PayOS payment API.
- Provider fallback trong script manual: FiinTrade, Vietstock datafeed, EODHD nếu có API key tương ứng.
- OpenAI: chỉ có biến môi trường/hook trong `LLMService`, chưa có logic gọi API thật.

## 4. Luồng hoạt động tổng quan

Luồng dữ liệu theo thiết kế trong source:

```text
Vietstock / provider ngoài
        │
        ▼
crawler Python
        │
        ├── Parse dữ liệu market price, financial, trading stats, BCTT
        ├── Tùy chọn ghi Google Sheets
        └── Ghi MongoDB bằng PyMongo
                │
                ▼
MongoDB
        │
        ▼
API Node.js / Express / Mongoose
        │
        ▼
Client gọi REST API
```

API không trực tiếp crawl dữ liệu. API đọc và ghi MongoDB cho các nghiệp vụ người dùng, watchlist, dashboard, subscription và stock catalog.

Crawler có hai kiểu luồng:

- Daily crawler qua `python run.py`: dự định đọc danh sách stock từ MongoDB hoặc Google Sheets, crawl từng mã, ghi `factMarketPrices`, `crawlLogs`, `crawlLogDetails`, `factCrawlQualities`, tùy chọn ghi Google Sheets và chạy thêm market overview. Tuy nhiên source hiện tại của `app.py` có lỗi cú pháp nên `python run.py` chưa chạy được.
- Manual crawler qua `manual_crawl_by_date_improved.py`: dự định crawl dữ liệu HOSE theo ngày bất kỳ từ Vietstock/browser và provider fallback, ghi `factMarketPrices` và log chất lượng. File này qua được `py_compile`, nhưng phần `main()` hiện tham chiếu một số biến chưa khởi tạo nên có thể lỗi runtime.
- Market overview crawler qua `scripts/market_overview_crawler.py`: mở trang KQGD Vietstock, bắt API `/data/KQGDThongKeGiaStockPaging`, chuẩn hóa dòng mới nhất và in kết quả. Job `market_overview_daily.py` có thể gọi script này rồi upsert vào collection `market_overviews`.

Không thấy queue/message broker trong source code. Không thấy Dockerfile, docker-compose hoặc Makefile.

## 5. Chi tiết folder `api`

### Mục đích

`api` là REST API service cho hệ thống backend. API chịu trách nhiệm:

- Đăng ký, đăng nhập, refresh token, logout.
- Google OAuth sign-in/sign-up.
- Quản lý profile user và quản trị user.
- Tra cứu danh mục cổ phiếu và lịch sử giá.
- Quản lý watchlist theo gói FREE/PRO.
- Dashboard theo role USER, STAFF, ADMIN.
- Tạo thanh toán subscription bằng PayOS và nhận webhook.

### Entry point và cấu hình server

- `src/server.js`:
  - Gọi `connectDB()` để kết nối MongoDB.
  - Gọi `seedRolesAndUsers()` để tạo role và user mặc định.
  - Start Express app ở `appConfig.port`, mặc định `5000`.
  - Có graceful shutdown cho `SIGTERM` và `SIGINT`.

- `src/app.js`:
  - Cấu hình `helmet({ contentSecurityPolicy: false })`.
  - Cấu hình CORS từ `appConfig.corsOptions`.
  - Cấu hình `morgan`.
  - Cấu hình `express-session` và Passport.
  - Cấu hình raw body cho `POST /api/subscriptions/webhook` trước `express.json()`.
  - Mount Swagger UI tại `/api-docs`.
  - Mount các router thật sự đang hoạt động.

Các router được mount trong `app.js`:

```text
/api/auth
/api/users
/api/admin/users
/api/stocks
/api/admin/stocks
/api/watchlists
/api/dashboard
/api/subscriptions
```

Các module có folder/file nhưng hiện đang trống 0 byte và chưa được mount:

```text
roles
markets
industries
data-sources
financials
crawl-jobs
crawl-logs
market-overview
```

### Middleware và bảo mật

- `auth.middleware.js`: kiểm tra `Authorization: Bearer <token>`, verify access token, load user từ MongoDB và chặn user không `ACTIVE`.
- `role.middleware.js`: kiểm tra role theo danh sách cho phép.
- `subscription.middleware.js`: nếu user PRO đã hết hạn thì tự downgrade về FREE và set `subscription_status = EXPIRED`.
- `error.middleware.js`: trả response lỗi chuẩn, chỉ kèm stack khi `NODE_ENV=development`.
- `helmet`: bật security headers, nhưng tắt CSP để Swagger UI dùng inline assets.
- CORS: nếu không có `CORS_ORIGINS`, API reflect origin và cho credentials.

### Authentication

Auth local:

- Register tạo user role `USER`.
- Login kiểm tra email/password bằng `bcryptjs`.
- Access token payload gồm `user_id`, `email`, `role`, `plan`.
- Refresh token được hash và lưu vào `users.refresh_token_hash`.
- Logout xóa `refresh_token_hash`.

Google OAuth:

- Dùng Passport Google OAuth 2.0.
- Sign-in route `/api/auth/google`.
- Sign-up route `/api/auth/google/register`.
- Callback redirect về `GOOGLE_OAUTH_SUCCESS_REDIRECT` với one-time `code`.
- Frontend gọi `POST /api/auth/oauth/exchange` để đổi code lấy JWT.
- One-time code được lưu trong memory `oauth-exchange.store.js`, TTL 5 phút, single-use. Chưa có Redis hoặc shared store cho nhiều instance.

### Subscription và PayOS

- `plan.config.js` định nghĩa:
  - FREE: tối đa 5 stock trong watchlist.
  - PRO: tối đa 50 stock trong watchlist.
  - Giá subscription: `50000` VND.
  - Thời hạn: 30 ngày.
- `subscriptions.service.js` tạo payment PayOS và lưu `payos_order_code`, `payos_payment_link_id` vào user.
- Webhook PayOS public, hỗ trợ payload thật `{ data, signature }` có verify và payload test đơn giản `{ orderCode, status }`.
- Biến `PAYOS_PRO_PRICE` có trong `env.config.js` nhưng source hiện tại không dùng để tính giá; giá thực tế lấy từ `SUBSCRIPTION_PRICE` trong `plan.config.js`.

### Database connection

- `database.config.js` dùng `mongoose.connect(env.MONGODB_URI)`.
- Mặc định nếu thiếu `MONGODB_URI`: `mongodb://localhost:27017/aistock`.
- API dùng Mongoose models trong `src/database/models`.

### Seed dữ liệu

`server.js` chỉ tự gọi `seed-roles.js`.

`seed-roles.js` tạo role:

- `USER`
- `STAFF`
- `ADMIN`

Và tạo user phát triển mặc định nếu chưa tồn tại:

| Email | Role | Status | Ghi chú |
| --- | --- | --- | --- |
| `user@example.com` | USER | ACTIVE | User thường |
| `staff@example.com` | STAFF | ACTIVE | Staff |
| `admin@example.com` | ADMIN | ACTIVE | Admin |
| `locked@example.com` | USER | LOCKED | User bị khóa |
| `pro@example.com` | USER | ACTIVE, PRO | PRO còn hạn 30 ngày tính từ lúc seed |
| `expired@example.com` | USER | ACTIVE, PRO/EXPIRED | PRO đã hết hạn |

Các mật khẩu mặc định có trong source seed và chỉ nên dùng cho môi trường dev/test. Không dùng cho production.

`seed-markets.js` và `seed-industries.js` có tồn tại nhưng không được gọi trong `server.js`. Nếu cần seed market/industry phải gọi thủ công hoặc import thêm.

### Cách chạy API

```powershell
cd api
npm install
npm run dev
```

Hoặc:

```powershell
cd api
npm start
```

API mặc định chạy tại:

```text
http://localhost:5000
```

Swagger:

```text
http://localhost:5000/api-docs
```

Yêu cầu trước khi chạy ổn định:

- MongoDB đang chạy hoặc `MONGODB_URI` trỏ tới MongoDB hợp lệ.
- Nếu dùng Google OAuth, cấu hình đầy đủ Google env.
- Nếu dùng PayOS, cấu hình đầy đủ PayOS env.

## 6. Chi tiết folder `crawler`

### Mục đích

`crawler` thu thập dữ liệu chứng khoán từ Vietstock và ghi vào MongoDB/Google Sheets.

Các nhóm dữ liệu crawler xử lý:

- Market data từ trang profile Vietstock: giá hiện tại/close, open, high, low, volume, vốn hóa, nước ngoài mua/bán, EPS, P/E, P/B, ROE/ROAA/ROS.
- Financial data từ profile và tab BCTT nếu `ENABLE_FINANCIAL_DATA=true`.
- Trading statistics từ trang `/thong-ke-giao-dich.htm` nếu `ENABLE_TRADING_STATS=true`.
- Market overview/KQGD từ trang `ket-qua-giao-dich` của Vietstock.

### Entry point

- `run.py`: thêm `crawler/src` vào `sys.path`, import `vietstock_crawler.app.run` và gọi `run()`.
- `src/vietstock_crawler/app.py`: orchestration chính.

Trạng thái hiện tại:

- `python -m py_compile src/vietstock_crawler/app.py` lỗi:

```text
SyntaxError: expected 'except' or 'finally' block
```

- Lỗi nằm tại `src/vietstock_crawler/app.py`, dòng `elif result["status"] == "SKIPPED"` trong source hiện tại.
- Vì vậy `python run.py` hiện chưa chạy được cho tới khi sửa lỗi cú pháp.

### Nguồn dữ liệu

- Trang profile: được tạo bằng `make_company_url()` hoặc lấy từ `dimStockDataSources.market_price_data_url`.
- Trang trading stats: `https://finance.vietstock.vn/<SYMBOL>/thong-ke-giao-dich.htm`.
- Tab BCTT: `https://finance.vietstock.vn/<SYMBOL>/tai-chinh.htm?tab=BCTT`.
- Market overview: `https://finance.vietstock.vn/ket-qua-giao-dich?tab=thong-ke-gia&exchange=1&code=-19`.
- Provider fallback trong manual crawler:
  - `vietstock`
  - `fiintrade`
  - `vietstock_datafeed`
  - `eodhd`

### Lưu dữ liệu

MongoDB:

- `MongoDBService` kết nối bằng `pymongo.MongoClient(settings.mongodb_uri)`.
- Crawler ghi các collection:
  - `factMarketPrices`
  - `factFinancialStatements`
  - `factFinancialReportSources`
  - `crawlLogs`
  - `crawlLogDetails`
  - `factCrawlQualities`
  - `dimStockDataSources`
  - `dimReportPeriods`
  - `dimDataSources`
  - `market_overviews`

Google Sheets:

- Nếu `SAVE_TO_GSHEET=true`, crawler dùng service account và spreadsheet ID.
- Sheet cấu hình mặc định là `CONFIG`.
- Cột CONFIG được code mong đợi:

```text
symbol | slug | company_name_vi | profile_url | trading_stats_url
```

Output sheet:

```text
MARKET_DATA_dd_mm_yy
FINANCIAL_DATA_Qx_yyyy hoặc FINANCIAL_DATA_dd_mm_yy
TRADING_STATS_Qx_yyyy hoặc TRADING_STATS_dd_mm_yy
```

### Scheduling/automation

Trong source hiện tại không thấy cron hệ thống hoặc queue.

`ENABLE_DAILY_MARKET_OVERVIEW=true` khiến `app.py` dự định chạy thêm `run_daily_market_overview(db_service)` sau daily crawl, nhưng `app.py` hiện đang lỗi cú pháp.

Trong API có folder `crawl-jobs` và file `crawl-jobs.scheduler.js`, nhưng các file này hiện 0 byte, chưa có scheduler thật.

### Cách chạy crawler

Cài dependencies:

```powershell
cd crawler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Chạy daily crawler theo entry point có trong source:

```powershell
python run.py
```

Lưu ý: lệnh trên hiện bị chặn bởi lỗi cú pháp trong `src/vietstock_crawler/app.py`.

Chạy market overview crawler độc lập:

```powershell
python scripts\market_overview_crawler.py
```

Chạy manual crawler theo ngày:

```powershell
python manual_crawl_by_date_improved.py --date 2026-05-22 --delay 0.5
```

Chạy thử giới hạn:

```powershell
python manual_crawl_by_date_improved.py --date 2026-05-22 --limit 5 --dry-run
```

Lưu ý: `manual_crawl_by_date_improved.py` qua được `py_compile`, nhưng `main()` hiện có các biến chưa khởi tạo như `success_first`, `retry_symbols`, `skipped_list`, `success_retry`, `failed_retry`; retry phase còn dùng `slug`, `providers`, `market_id`, `industry_id` chưa định nghĩa trong scope. Cần sửa trước khi dùng ổn định.

## 7. Hướng dẫn cài đặt

### Yêu cầu runtime

- Node.js: Chưa xác định rõ trong source code.
- npm: cần để cài API dependencies.
- Python: `>=3.11`.
- MongoDB: cần một MongoDB local hoặc MongoDB Atlas.
- Playwright Chromium: cần cho crawler.

### Cài API

```powershell
cd api
npm install
```

Tạo file `.env` cho API. Source có thể đọc `.env` ở repo root hoặc ở thư mục chạy process. Nếu chạy `npm run dev` trong `api`, nên tạo `api/.env`.

Ví dụ tối thiểu:

```env
NODE_ENV=development
PORT=5000
MONGODB_URI=mongodb://localhost:27017/aistock
JWT_ACCESS_SECRET=change_me_access_secret
JWT_REFRESH_SECRET=change_me_refresh_secret
SESSION_SECRET=change_me_session_secret
```

### Cài crawler

```powershell
cd crawler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Tạo/cập nhật `crawler/.env`. File `.env` hiện có trong workspace nhưng không nên commit. Nếu dùng MongoDB theo default của settings thì cần thêm `MONGODB_URI`.

Ví dụ tối thiểu để crawler dùng MongoDB:

```env
MONGODB_URI=mongodb://localhost:27017/aistock
SAVE_TO_MONGODB=true
LOAD_CONFIG_FROM_MONGODB=true
SAVE_TO_GSHEET=false
```

Nếu dùng Google Sheets:

```env
SAVE_TO_GSHEET=true
GOOGLE_SHEET_ID=your_spreadsheet_id
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
CONFIG_SHEET_NAME=CONFIG
```

`crawler/service_account.json` là file credential nhạy cảm. Không đưa nội dung file này vào tài liệu, commit hoặc log.

## 8. Hướng dẫn chạy dự án

### Chạy API

```powershell
cd api
npm install
npm run dev
```

Kiểm tra:

```powershell
curl http://localhost:5000/
```

Response kỳ vọng:

```json
{"message":"AI Stock Trend Prediction API is running"}
```

Swagger:

```text
http://localhost:5000/api-docs
```

### Chạy Crawler

Daily crawler:

```powershell
cd crawler
.\.venv\Scripts\Activate.ps1
python run.py
```

Trạng thái hiện tại: lệnh này chưa chạy được vì lỗi cú pháp trong `src/vietstock_crawler/app.py`.

Market overview độc lập:

```powershell
cd crawler
.\.venv\Scripts\Activate.ps1
python scripts\market_overview_crawler.py
```

Manual crawl theo ngày:

```powershell
cd crawler
.\.venv\Scripts\Activate.ps1
python manual_crawl_by_date_improved.py --date 2026-05-22 --limit 5 --dry-run
```

Trạng thái hiện tại: script manual có thể lỗi runtime do biến chưa khởi tạo trong `main()`.

### Chạy toàn bộ dự án nếu có thể

Không có script root, Docker Compose hoặc Makefile để chạy toàn bộ dự án cùng lúc.

Cách chạy hiện tại là mở hai terminal:

Terminal 1:

```powershell
cd api
npm run dev
```

Terminal 2:

```powershell
cd crawler
.\.venv\Scripts\Activate.ps1
python run.py
```

Lưu ý: Terminal 2 cần sửa lỗi `app.py` trước.

## 9. Biến môi trường

### API

| Variable | Mục đích | Ví dụ an toàn | Bắt buộc |
| --- | --- | --- | --- |
| `NODE_ENV` | Môi trường chạy | `development` | Không, mặc định `development` |
| `PORT` | Cổng API | `5000` | Không, mặc định `5000` |
| `MONGODB_URI` | URI kết nối MongoDB | `mongodb://localhost:27017/aistock` | Không theo code, nhưng cần DB hợp lệ để API chạy |
| `JWT_ACCESS_SECRET` | Secret ký access token | `change_me_access_secret` | Nên bắt buộc ngoài dev |
| `JWT_REFRESH_SECRET` | Secret ký refresh token | `change_me_refresh_secret` | Nên bắt buộc ngoài dev |
| `JWT_ACCESS_EXPIRES_IN` | Thời hạn access token | `15m` | Không, mặc định `15m` |
| `JWT_REFRESH_EXPIRES_IN` | Thời hạn refresh token | `7d` | Không, mặc định `7d` |
| `BCRYPT_SALT_ROUNDS` | Số vòng salt bcrypt | `10` | Không, mặc định `10` |
| `CORS_ORIGINS` | Whitelist origin, phân tách bằng dấu phẩy | `http://localhost:3000` | Không |
| `SESSION_SECRET` | Secret cho express-session/OAuth state | `change_me_session_secret` | Nên bắt buộc ngoài dev |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | `xxx.apps.googleusercontent.com` | Chỉ cần nếu dùng Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | `GOCSPX-...` | Chỉ cần nếu dùng Google OAuth |
| `GOOGLE_CALLBACK_URL` | Callback URL Google OAuth | `http://localhost:5000/api/auth/google/callback` | Chỉ cần nếu dùng Google OAuth |
| `GOOGLE_OAUTH_SUCCESS_REDIRECT` | Frontend URL nhận `?code=` sau OAuth | `http://localhost:3000` | Không, mặc định `http://localhost:3000` |
| `GOOGLE_OAUTH_FAILURE_REDIRECT` | Frontend URL khi OAuth lỗi | `http://localhost:3000?error=google_auth_failed` | Không |
| `PAYOS_CLIENT_ID` | PayOS client ID | `payos_client_id` | Chỉ cần nếu tạo payment |
| `PAYOS_API_KEY` | PayOS API key | `payos_api_key` | Chỉ cần nếu tạo payment |
| `PAYOS_CHECKSUM_KEY` | PayOS checksum key | `payos_checksum_key` | Chỉ cần nếu verify webhook |
| `PAYOS_RETURN_URL` | URL quay lại khi thanh toán thành công | `http://localhost:3000/payment/success` | Không, có fallback |
| `PAYOS_CANCEL_URL` | URL quay lại khi hủy thanh toán | `http://localhost:3000/payment/cancel` | Không, có fallback |
| `PAYOS_PRO_PRICE` | Được parse trong env config | `50000` | Không; hiện không được dùng trong service |

### Crawler

| Variable | Mục đích | Ví dụ an toàn | Bắt buộc |
| --- | --- | --- | --- |
| `MONGODB_URI` | URI MongoDB cho PyMongo | `mongodb://localhost:27017/aistock` | Có nếu `SAVE_TO_MONGODB=true` hoặc `LOAD_CONFIG_FROM_MONGODB=true` |
| `MONGODB_DB_NAME` | DB name cho manual crawler | `aistock` | Không |
| `SAVE_TO_MONGODB` | Bật ghi MongoDB | `true` | Không, mặc định `true` |
| `LOAD_CONFIG_FROM_MONGODB` | Load danh sách stock từ `dimstocks` | `true` | Không, mặc định `true` |
| `SAVE_TO_GSHEET` | Bật ghi Google Sheets | `false` | Không, mặc định `false` |
| `GOOGLE_SHEET_ID` | Spreadsheet ID | `your_spreadsheet_id` | Có nếu ghi/đọc Google Sheets |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Đường dẫn service account JSON | `service_account.json` | Có nếu ghi/đọc Google Sheets |
| `CONFIG_SHEET_NAME` | Tên sheet cấu hình | `CONFIG` | Không, mặc định `CONFIG` |
| `REQUEST_DELAY_SECONDS` | Delay giữa các symbol | `1.5` | Không |
| `PAGE_WAIT_MS` | Thời gian đợi page sau khi load | `2000` | Không |
| `PAGE_TIMEOUT_MS` | Timeout page Playwright | `60000` | Không |
| `SYMBOL_CRAWL_TIMEOUT` | Timeout mỗi mã | `90` | Không |
| `MAX_PAGE_RETRIES` | Số lần retry mở page | `2` | Không |
| `PAGE_RETRY_SLEEP_SECONDS` | Delay giữa các retry | `5` | Không |
| `PLAYWRIGHT_WAIT_UNTIL` | Điều kiện wait của Playwright | `domcontentloaded` | Không |
| `BCTT_PAGE_WAIT_MS` | Thời gian đợi tab BCTT | `2500` | Không |
| `GSHEET_MAX_RETRIES` | Retry khi Google Sheets quota 429 | `6` | Không |
| `GSHEET_RETRY_BASE_SECONDS` | Delay base khi retry Google Sheets | `65` | Không |
| `APPLY_FORMATS` | Bật format Google Sheets | `false` | Không |
| `FORMAT_NUMBER_COLUMNS` | Format cột số trong Google Sheets | `true` | Không |
| `TRADING_STATS_WEEKDAY` | Thứ chạy trading stats theo `datetime.weekday()` | `4` | Không |
| `TRADING_STATS_MIN_DAILY_RUN` | Lần chạy tối thiểu trong ngày để chạy trading stats | `2` | Không |
| `FORCE_RUN_TRADING_STATS` | Ép chạy trading stats | `false` | Không |
| `FORCE_REFRESH_TRADING_STATS` | Ép refresh trading stats dù sheet đủ dòng | `false` | Không |
| `ENABLE_FINANCIAL_DATA` | Crawl financial data | `false` | Không |
| `ENABLE_TRADING_STATS` | Crawl trading stats | `false` | Không |
| `CREATE_QUARTERLY_FINANCIAL_TRADING_SHEETS` | Ghi financial/trading theo sheet quý | `true` | Không |
| `FINANCIAL_TRADING_SHEETS_BY_QUARTER` | Alias cho cấu hình sheet quý | `false` | Không |
| `QUARTERLY_FINANCIAL_TRADING_SHEETS` | Alias cho cấu hình sheet quý | `false` | Không |
| `USE_LATEST_REPORTED_QUARTER_FOR_SHEETS` | Lấy suffix sheet theo quý mới nhất parse được | `true` | Không |
| `ALLOW_INCOMPLETE_CURRENT_QUARTER_SHEET` | Cho phép quý hiện tại chưa hoàn tất | `false` | Không |
| `QUARTER_SHEET_OVERRIDE` | Override suffix quý | `Q1_2026` | Không |
| `BLOCK_ADS` | Chặn tài nguyên quảng cáo | `true` | Không |
| `CLOSE_POPUPS` | Cố đóng popup | `true` | Không |
| `ENABLE_LLM` | Bật hook LLM | `false` | Không |
| `OPENAI_API_KEY` | API key cho hook LLM | `sk-...` | Chưa dùng thực tế |
| `OPENAI_MODEL` | Model name cho hook LLM | `gpt-5.5` | Không; hook chưa gọi API |
| `DRY_RUN` | Không ghi DB/Google Sheets | `true` | Không |
| `CRAWL_LIMIT` | Giới hạn số mã crawl | `5` | Không |
| `ENABLE_DAILY_MARKET_OVERVIEW` | Chạy thêm market overview sau daily crawl | `true` | Không |
| `FIINTRADE_API_URL` | Provider fallback FiinTrade | `https://...` | Chỉ nếu dùng provider |
| `FIINTRADE_API_KEY` | API key FiinTrade | `...` | Chỉ nếu dùng provider |
| `VIETSTOCK_DATAFEED_API_URL` | Provider fallback Vietstock datafeed | `https://...` | Chỉ nếu dùng provider |
| `VIETSTOCK_DATAFEED_API_KEY` | API key Vietstock datafeed | `...` | Chỉ nếu dùng provider |
| `EODHD_API_KEY` | API key EODHD | `...` | Chỉ nếu dùng provider |

## 10. Database / dữ liệu

Dự án dùng MongoDB.

### Collections/API models

Operational:

- `users`: user, role, email, password hash, Google ID, status, refresh token hash, plan/subscription, PayOS metadata.
- `roles`: role `USER`, `STAFF`, `ADMIN`.
- `watchlists`: mapping `user_id` và `stock_id`, unique theo user/stock.
- `crawlJobs`: schema job crawl, nhưng API module hiện trống.
- `crawlLogs`: log tổng quát mỗi lần crawl.
- `crawlLogDetails`: log chi tiết theo symbol.

Dimension:

- `dimTimes`: ngày giao dịch với `time_id = YYYYMMDD`.
- `dimMarkets`: sàn giao dịch, ví dụ HOSE/HNX/UPCOM.
- `dimIndustries`: ngành.
- `dimstocks`: stock master data.
- `dimStockDataSources`: URL crawl theo stock.
- `dimReportPeriods`: kỳ báo cáo tài chính.
- `dimDataSources`: crawler tạo/dùng collection này, nhưng API hiện không có Mongoose model tương ứng.

Fact:

- `factMarketPrices`: OHLCV, volume, foreign buy/sell/net, market cap, EPS, P/E, P/B, ROE/ROAA/ROS, price change.
- `factFinancialStatements`: dữ liệu báo cáo tài chính đã chuẩn hóa theo stock/kỳ báo cáo/source.
- `factFinancialReportSources`: dữ liệu BCTT/raw source theo stock/kỳ/source URL.
- `factCrawlQualities`: thống kê chất lượng phiên crawl.
- `factMarketOverviews`: có Mongoose model trong API, nhưng dashboard/crawler hiện dùng collection khác là `market_overviews`.
- `market_overviews`: collection PyMongo dùng cho KQGD/market overview; dashboard đọc trực tiếp collection này bằng `mongoose.connection.db.collection('market_overviews')`.

### Index/unique constraint trong schema

- `watchlists`: unique `{ user_id, stock_id }`.
- `dimstocks`: unique `{ market_id, symbol }` và `symbol` unique.
- `factMarketPrices`: unique `{ stock_id, time_id, data_source_id }`.
- `factFinancialStatements`: unique `{ stock_id, report_period_id, data_source_id }`.
- `factFinancialReportSources`: unique `{ stock_id, report_period_id, source_url }`.
- `factMarketOverviews`: unique `{ market_id, time_id }`.
- `market_overviews`: PyMongo tạo index unique `{ trading_date, symbol }`.

### Cách dữ liệu được tạo/cập nhật

- API tạo/cập nhật `users`, `watchlists`, `dimstocks`, subscription fields trên `users`.
- Crawler tạo/cập nhật `factMarketPrices`, `factFinancialStatements`, `factFinancialReportSources`, `crawlLogs`, `crawlLogDetails`, `factCrawlQualities`, `dimStockDataSources`, `dimReportPeriods`, `market_overviews`.
- Dashboard API tổng hợp dữ liệu từ `watchlists`, `factMarketPrices`, `crawlLogs`, `crawlJobs`, `dimstocks`, `dimMarkets`, `dimStockDataSources`, `market_overviews`.

## 11. API endpoints

Các endpoint dưới đây là những route được mount thực tế trong `api/src/app.js`.

| Method | Endpoint | Mục đích | Request body/query | Response |
| --- | --- | --- | --- | --- |
| GET | `/` | Health check | Không | `{ message }` |
| GET | `/api-docs` | Swagger UI | Không | HTML Swagger |
| POST | `/api/auth/register` | Đăng ký user | Body: `full_name`, `email`, `password` | `{ success, message, data.user }` |
| POST | `/api/auth/login` | Đăng nhập | Body: `email`, `password` | `{ access_token, refresh_token, user }` |
| POST | `/api/auth/logout` | Logout | Bearer token | `{ success, message }` |
| POST | `/api/auth/refresh-token` | Lấy access token mới | Body: `refresh_token` | `{ access_token }` |
| GET | `/api/auth/google` | Bắt đầu Google OAuth sign-in | Không | Redirect 302 |
| GET | `/api/auth/google/register` | Bắt đầu Google OAuth sign-up | Không | Redirect 302 |
| GET | `/api/auth/google/callback` | Callback Google OAuth | Google redirect params | Redirect về frontend với `code` hoặc `error` |
| GET | `/api/auth/google/oauth-config` | Xem callback URL trong dev | Chỉ khi `NODE_ENV=development` | `{ GOOGLE_CALLBACK_URL, hints }` |
| POST | `/api/auth/oauth/exchange` | Đổi OAuth one-time code lấy JWT | Body: `code` | `{ access_token, refresh_token, user }` |
| GET | `/api/users/me` | Xem profile | Bearer token | User profile |
| PUT | `/api/users/me` | Cập nhật profile | Body: `full_name` | User profile |
| PUT | `/api/users/me/password` | Đổi password | Body: `current_password`, `new_password` | `{ success, message }` |
| GET | `/api/admin/users` | Admin list/search user | Query: `page`, `limit`, `keyword`, `status`, `role` | `{ items, pagination }` |
| GET | `/api/admin/users/:id` | Admin xem user | Path: `id` | User detail |
| PATCH | `/api/admin/users/:id/lock` | Admin khóa user | Path: `id` | `{ success, message }` |
| PATCH | `/api/admin/users/:id/unlock` | Admin mở khóa user | Path: `id` | `{ success, message }` |
| PATCH | `/api/admin/users/:id/role` | Admin đổi role | Body: `role` = `USER` hoặc `STAFF` | User profile |
| GET | `/api/stocks` | Danh sách cổ phiếu | Query: `page`, `limit`, `keyword`, `market` | `{ items, pagination }` |
| GET | `/api/stocks/:symbol` | Chi tiết cổ phiếu và latest price | Path: `symbol` | Stock detail |
| GET | `/api/stocks/:symbol/chart` | Lịch sử OHLCV | Query: `range` = `7d`, `1m`, `3m`, `6m`, `1y`, `all` | Array candle data |
| POST | `/api/admin/stocks` | Admin tạo stock master | Body: `symbol`, `company_name`, `market_id`, optional `industry_id`, `status`, `listed_date` | Created stock |
| PUT | `/api/admin/stocks/:id` | Admin cập nhật stock | Path: `id`, body fields optional | Updated stock |
| GET | `/api/watchlists` | Xem watchlist | Bearer token | `{ items, limit, currentCount, overLimit }` |
| POST | `/api/watchlists` | Thêm stock vào watchlist | Body: `symbol` | `{ watchlist_id, symbol, created_at }` |
| DELETE | `/api/watchlists/:symbol` | Xóa stock khỏi watchlist | Path: `symbol` | `{ success, message }` |
| POST | `/api/watchlists/trim` | Cắt watchlist còn các stock được giữ | Body: `keepStockIds` array | `{ deletedCount, remainingCount }` |
| GET | `/api/dashboard/user` | Dashboard USER | Bearer token role `USER` | Watchlist, market leaders, market overview |
| GET | `/api/dashboard/staff` | Dashboard STAFF | Bearer token role `STAFF` | Crawl stats/catalog/recent activities |
| GET | `/api/dashboard/admin` | Dashboard ADMIN | Bearer token role `ADMIN` | User/watchlist/catalog/system health |
| POST | `/api/subscriptions/create-payment` | Tạo checkout PayOS | Bearer token, body `amount` optional nhưng service không dùng | PayOS checkout info |
| POST | `/api/subscriptions/webhook` | Nhận webhook PayOS | Public raw JSON | `{ success, message, data/error }` |
| GET | `/api/subscriptions/status` | Xem trạng thái subscription | Bearer token | `{ plan, subscriptionStatus, subscriptionExpiresAt }` |

Các module `roles`, `markets`, `industries`, `data-sources`, `financials`, `crawl-jobs`, `crawl-logs`, `market-overview` chưa có endpoint chạy được vì file route/controller/service/repository hiện trống và không được mount.

## 12. Cách kiểm tra hoạt động

### Kiểm tra API

Cài dependency và chạy:

```powershell
cd api
npm install
npm run dev
```

Health check:

```powershell
curl http://localhost:5000/
```

Swagger:

```text
http://localhost:5000/api-docs
```

Login bằng user seed dev:

```powershell
curl -X POST http://localhost:5000/api/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"email\":\"user@example.com\",\"password\":\"user123456\"}"
```

Kiểm tra profile sau khi lấy access token:

```powershell
curl http://localhost:5000/api/users/me `
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Kiểm tra cú pháp JavaScript:

```powershell
cd api
$files = rg --files -g "*.js" -g "!node_modules/**"
foreach ($f in $files) { node --check $f }
```

Kết quả đã kiểm tra trong workspace hiện tại: không phát hiện lỗi cú pháp JS bằng `node --check`.

Lưu ý: `npm test` trong `api/package.json` trỏ tới các file `test/test-auth-flow.js`, `test/test-users-flow.js`, `test/test-stocks-watchlist-flow.js`, nhưng thư mục/file `api/test` không có trong source hiện tại. Vì vậy script test này có khả năng lỗi.

### Kiểm tra Crawler

Sau khi cài dependencies:

```powershell
cd crawler
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Kết quả thử trong workspace hiện tại:

- Với Python hệ thống và `.venv`, test collection lỗi vì thiếu module `bson`.
- Cần chạy `pip install -r requirements.txt` trong đúng venv trước.

Kiểm tra cú pháp app chính:

```powershell
cd crawler
python -m py_compile src\vietstock_crawler\app.py
```

Kết quả hiện tại:

```text
SyntaxError: expected 'except' or 'finally' block
```

Kiểm tra script manual:

```powershell
cd crawler
python -m py_compile manual_crawl_by_date_improved.py
```

Kết quả hiện tại: file qua được compile, nhưng vẫn có rủi ro lỗi runtime như đã nêu ở phần crawler.

Kiểm tra market overview:

```powershell
cd crawler
python scripts\market_overview_crawler.py
```

Nếu chạy thành công, terminal sẽ in `Parsed trading date` và object `Normalized Result`.

Kiểm tra dữ liệu MongoDB mẫu:

```powershell
cd crawler
python inspect_db.py
```

Script này đọc `MONGODB_URI` từ `.env`, sau đó in sample từ `dimstocks` và `dimStockDataSources`.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân trong source hiện tại | Cách xử lý |
| --- | --- | --- |
| API không start được vì MongoDB | `server.js` gọi `connectDB()` trước khi listen | Kiểm tra `MONGODB_URI`, MongoDB local/Atlas, network và credential |
| Port 5000 đã dùng | `PORT` mặc định là `5000` | Đổi `PORT` trong `.env` |
| Google OAuth `redirect_uri_mismatch` | `GOOGLE_CALLBACK_URL` không khớp Google Console | Dùng `/api/auth/google/oauth-config` trong dev để copy URL chính xác |
| `Google OAuth is not configured` | Thiếu `GOOGLE_CLIENT_ID` hoặc `GOOGLE_CLIENT_SECRET` | Cấu hình Google OAuth env |
| User bị 403 | `auth.middleware.js` chặn user không `ACTIVE` hoặc role không đủ | Kiểm tra `users.status` và role |
| Watchlist vượt giới hạn | FREE giới hạn 5, PRO giới hạn 50 | Nâng plan hoặc gọi `/api/watchlists/trim` |
| PayOS create payment lỗi | Thiếu PayOS credential hoặc PayOS API lỗi | Cấu hình `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, `PAYOS_CHECKSUM_KEY` |
| `npm test` lỗi missing file | `package.json` trỏ tới `api/test/...` nhưng source không có | Tạo lại test files hoặc cập nhật script test |
| `python run.py` lỗi cú pháp | `crawler/src/vietstock_crawler/app.py` đang có `elif` sai vị trí | Sửa block `try/except` quanh dòng lỗi |
| `pytest` lỗi `ModuleNotFoundError: bson` | Chưa cài `pymongo` trong environment hiện tại | Chạy `pip install -r requirements.txt` trong venv |
| `manual_crawl_by_date_improved.py` lỗi `NameError` | Một số biến trong `main()` chưa được khởi tạo | Khởi tạo `success_first`, `retry_symbols`, `skipped_list`, `success_retry`, `failed_retry` và sửa retry scope |
| Crawler thiếu `MONGODB_URI` | Settings mặc định `SAVE_TO_MONGODB=true` và `LOAD_CONFIG_FROM_MONGODB=true` | Thêm `MONGODB_URI` hoặc tắt các flag MongoDB |
| Google Sheets quota 429 | Google Sheets write quota | Tăng/giữ `GSHEET_MAX_RETRIES`, `GSHEET_RETRY_BASE_SECONDS` |
| Không tìm thấy service account | `GOOGLE_SERVICE_ACCOUNT_FILE` trỏ sai file | Đặt đúng path và share Google Sheet cho service account |
| Crawler bị Vietstock timeout/popup | Playwright mở trang động, có quảng cáo/popup | Điều chỉnh `PAGE_TIMEOUT_MS`, `MAX_PAGE_RETRIES`, `BLOCK_ADS`, `CLOSE_POPUPS` |
| `init_market_overviews_from_json.py` không chạy | File `crawler/scripts/marketoverview.json` không tồn tại trong repo | Bổ sung file JSON đúng cấu trúc hoặc không dùng script này |
| Market overview dashboard không có dữ liệu | Dashboard đọc collection `market_overviews` | Chạy market overview crawler/job để upsert dữ liệu |

## 14. Ghi chú cho developer

- Thêm route API mới: tạo module trong `api/src/modules/<module>` và mount router trong `api/src/app.js`.
- Cập nhật auth/role: xem `api/src/common/middlewares/auth.middleware.js`, `role.middleware.js`, `api/src/common/utils/jwt.util.js`, `api/src/modules/auth`.
- Cập nhật plan/watchlist limit: xem `api/src/config/plan.config.js` và `api/src/modules/watchlists`.
- Cập nhật subscription/PayOS: xem `api/src/modules/subscriptions`.
- Cập nhật schema MongoDB: xem `api/src/database/models`.
- Cập nhật crawler parse profile/trading/BCTT: xem `crawler/src/vietstock_crawler/parsers` và `services/vietstock_service.py`.
- Cập nhật ghi MongoDB từ crawler: xem `crawler/src/vietstock_crawler/services/mongodb_service.py`.
- Cập nhật Google Sheets output columns: xem `crawler/src/vietstock_crawler/models/columns.py`.
- Cập nhật market overview: xem `crawler/scripts/market_overview_crawler.py`, `crawler/src/vietstock_crawler/jobs/market_overview_daily.py`, `crawler/src/vietstock_crawler/utils/market_overview_utils.py`.

Các điểm nên cải thiện:

- Sửa lỗi cú pháp trong `crawler/src/vietstock_crawler/app.py`.
- Sửa runtime bug trong `manual_crawl_by_date_improved.py`.
- Bổ sung hoặc sửa `api/package.json` test scripts vì test files hiện không tồn tại.
- Quyết định một collection thống nhất cho market overview: `factMarketOverviews` hoặc `market_overviews`.
- Bổ sung Mongoose model cho `dimDataSources` nếu crawler/API tiếp tục dùng collection này.
- Mount hoặc xóa các module API đang trống để tránh hiểu nhầm.
- Không dùng default JWT/session secrets trong production.
- Thay memory OAuth exchange store bằng Redis nếu chạy nhiều API instance.
- Thêm `.env.example` thật cho `api` và `crawler`.
- Bổ sung Docker/Makefile/root scripts nếu muốn chạy toàn bộ hệ thống thống nhất.

## 15. Tóm tắt nhanh cách chạy

API:

```powershell
cd api
npm install
npm run dev
```

Kiểm tra API:

```powershell
curl http://localhost:5000/
```

Crawler setup:

```powershell
cd crawler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Crawler daily theo source:

```powershell
python run.py
```

Lưu ý: cần sửa lỗi cú pháp trong `crawler/src/vietstock_crawler/app.py` trước khi lệnh `python run.py` chạy được.

Market overview độc lập:

```powershell
python scripts\market_overview_crawler.py
```

Manual crawl theo ngày:

```powershell
python manual_crawl_by_date_improved.py --date 2026-05-22 --limit 5 --dry-run
```

Lưu ý: cần sửa các biến chưa khởi tạo trong `manual_crawl_by_date_improved.py` trước khi dùng ổn định.
