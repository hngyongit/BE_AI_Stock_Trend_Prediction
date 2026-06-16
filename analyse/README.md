# Analyse Service

## 1. Mục Đích

`analyse` là scaffold Python cho tầng phân tích AI/LLM của dự án `BE_AI_Stock_Trend_Prediction`.

Thư mục này được chuẩn bị để sau này nhận dữ liệu cổ phiếu từ client hoặc lấy dữ liệu từ backend API hiện có, chuẩn hóa dữ liệu, tạo prompt chất lượng cao, gọi OpenAI bằng `OPENAI_API_KEY`, rồi trả về báo cáo phân tích chứng khoán bằng tiếng Việt dưới dạng JSON có cấu trúc.

Hiện tại đây chỉ là skeleton. Chưa có logic phân tích tài chính, chưa có tính toán xu hướng, chưa gọi OpenAI thật và chưa fetch dữ liệu thật từ backend.

## 2. Vai Trò Trong Hệ Thống

Luồng hệ thống dự kiến:

```text
crawler → MongoDB → api → analyse → frontend/client
```

Vai trò từng phần:

- `crawler`: thu thập dữ liệu Vietstock, ghi `factMarketPrices`, `factFinancialStatements`, `factFinancialReportSources`, `crawlLogs`, `factCrawlQualities` và `market_overviews`.
- `api`: Node.js/Express/Mongoose REST API, cung cấp stock detail, chart, watchlist và dashboard qua wrapper `{ success, message, data }`.
- `analyse`: service Python độc lập, mặc định chạy port `5100`, dùng dữ liệu từ client hoặc từ `api` để chuẩn bị phân tích AI/LLM.

Các route backend đã xác minh từ source:

- `GET /api/stocks`: danh sách cổ phiếu, trả về `data.items` và `data.pagination`.
- `GET /api/stocks/:symbol`: thông tin stock master và `latest_price`.
- `GET /api/stocks/:symbol/chart?range=1m`: lịch sử OHLCV dạng `time/open/high/low/close/volume`.
- `GET /api/watchlists`: watchlist của user, yêu cầu Bearer token.
- `GET /api/dashboard/user`: dashboard user, gồm `watchlist`, `market_leaders`, `market_overview`, yêu cầu Bearer token role `USER`.

Các route `financials`, `crawl-logs`, `crawl-jobs`, `market-overview`, `markets`, `industries`, `roles`, `data-sources` hiện có file trong `api/src/modules` nhưng đang rỗng hoặc chưa được mount trong `api/src/app.js`, nên chưa thể xem là nguồn API chạy được.

## 3. Cấu Trúc Thư Mục

```text
analyse/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── run.py
├── src/
│   └── analyse/
│       ├── main.py
│       ├── app.py
│       ├── api/
│       ├── clients/
│       ├── config/
│       ├── constants/
│       ├── prompts/
│       ├── schemas/
│       ├── services/
│       ├── utils/
│       └── examples/
└── tests/
```

Ý nghĩa chính:

- `api`: route/controller FastAPI placeholder.
- `clients`: skeleton gọi backend API và OpenAI.
- `config`: đọc biến môi trường.
- `prompts`: template prompt LLM tương lai.
- `schemas`: Pydantic request/response schema.
- `services`: stub phân tích stock, watchlist, risk và portfolio plan.
- `utils`: helper JSON, prompt, số và response.
- `examples`: request/response mẫu bằng tiếng Việt.

## 4. Luồng Xử Lý Dữ Liệu Dự Kiến

Direct data mode:

```text
client → POST /api/analyse/stock → validate schema → normalize → build prompt → OpenAI → JSON response
```

Backend fetch mode:

```text
client → POST /api/analyse/fetch-and-analyse/stock
       → fetch /api/stocks/:symbol và /api/stocks/:symbol/chart
       → normalize → build prompt → OpenAI → JSON response
```

Watchlist mode:

```text
client → POST /api/analyse/watchlist
       → normalize danh sách mã
       → prompt so sánh rủi ro/cơ hội
       → OpenAI → kế hoạch theo dõi
```

## 5. Công Nghệ Sử Dụng

- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic
- pydantic-settings
- python-dotenv
- httpx
- OpenAI Python SDK
- pytest

## 6. Cách Cài Đặt

Windows PowerShell:

```powershell
cd analyse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

Bash/macOS/Linux:

```bash
cd analyse
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Service mặc định chạy tại:

```text
http://localhost:5100
```

## 7. Biến Môi Trường

```env
NODE_ENV=development
ANALYSE_HOST=0.0.0.0
ANALYSE_PORT=5100
PYTHONPATH=src

BACKEND_API_URL=http://localhost:5000
BACKEND_API_TOKEN=

OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TEMPERATURE=0.2
OPENAI_TIMEOUT_MS=60000
```

Lưu ý:

- Không commit `.env`.
- Không ghi `OPENAI_API_KEY` vào log, response hoặc tài liệu công khai.
- Skeleton hiện không yêu cầu API key thật để chạy.

## 8. Cách Chạy Service Skeleton

```powershell
cd analyse
.\.venv\Scripts\Activate.ps1
python run.py
```

Swagger UI của service:

```text
http://localhost:5100/api/analyse/docs
```

## 9. API Endpoints Dự Kiến

| Method | Endpoint | Trạng thái |
| --- | --- | --- |
| `GET` | `/` | Health/root placeholder |
| `GET` | `/api/analyse/health` | Health placeholder |
| `POST` | `/api/analyse/stock` | Nhận dữ liệu trực tiếp, trả phân tích placeholder |
| `POST` | `/api/analyse/watchlist` | Nhận watchlist, trả phân tích placeholder |
| `POST` | `/api/analyse/fetch-and-analyse/stock` | Khai báo fetch mode, chưa gọi backend thật |

Kiểm tra health:

```bash
curl http://localhost:5100/api/analyse/health
```

Kiểm tra stock placeholder:

```bash
curl -X POST http://localhost:5100/api/analyse/stock \
  -H "Content-Type: application/json" \
  -d @src/analyse/examples/sample_stock_request.json
```

Kiểm tra watchlist placeholder:

```bash
curl -X POST http://localhost:5100/api/analyse/watchlist \
  -H "Content-Type: application/json" \
  -d @src/analyse/examples/sample_watchlist_request.json
```

PowerShell:

```powershell
curl.exe -X POST http://localhost:5100/api/analyse/stock `
  -H "Content-Type: application/json" `
  -d "@src/analyse/examples/sample_stock_request.json"
```

## 10. Ví Dụ Request/Response

Single stock request nằm tại:

```text
src/analyse/examples/sample_stock_request.json
```

Watchlist request nằm tại:

```text
src/analyse/examples/sample_watchlist_request.json
```

Response mẫu nằm tại:

```text
src/analyse/examples/sample_analysis_result.json
```

Response hiện tại là placeholder. Ví dụ `trend.direction` mặc định là `UNCLEAR` vì chưa có OpenAI và chưa có logic phân tích xu hướng.

## 11. Cách Tích Hợp OpenAI Trong Bước Tiếp Theo

Các file đã chuẩn bị:

- `clients/openai_client.py`: client skeleton, có `generate_json_analysis(...)`.
- `config/openai_config.py`: gom `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE`, `OPENAI_TIMEOUT_MS`.
- `prompts/system_prompt.py`: nguyên tắc hệ thống cho LLM.
- `prompts/stock_analysis_prompt.py`: prompt cho một mã cổ phiếu.
- `prompts/watchlist_analysis_prompt.py`: prompt cho watchlist.
- `schemas/analysis_output_schema.py`: shape JSON kỳ vọng.

Khi triển khai thật, cần:

- Bắt buộc LLM trả JSON hợp lệ.
- Validate JSON bằng Pydantic trước khi trả cho client.
- Xử lý timeout và lỗi OpenAI.
- Không log dữ liệu nhạy cảm hoặc API key.
- Ghi rõ khi dữ liệu thiếu, cũ hoặc mâu thuẫn.

## 12. Nguyên Tắc Prompt LLM

Prompt hệ thống tương lai phải nhấn mạnh:

- Chỉ phân tích dựa trên dữ liệu được cung cấp.
- Không bịa dữ kiện tài chính không có trong payload.
- Luôn nêu rõ dữ liệu thiếu, cũ, không nhất quán hoặc chất lượng thấp.
- Không cam kết lợi nhuận.
- Không đưa lệnh mua/bán tuyệt đối.
- Không tuyên bố chắc chắn.
- Chỉ hỗ trợ giáo dục và ra quyết định.
- Output phải là JSON hợp lệ bằng tiếng Việt.
- Không Markdown, không code fence, không bình luận ngoài JSON.

## 13. Lưu Ý Bảo Mật

- `OPENAI_API_KEY` chỉ đọc từ biến môi trường.
- Không gửi API key về client.
- Không in API key trong exception/log.
- `BACKEND_API_TOKEN` nếu dùng phải được bảo vệ như Bearer token của user/service account.
- Khi gọi `/api/watchlists` hoặc `/api/dashboard/user`, cần token hợp lệ từ backend hiện có.

## 14. Những Phần Hiện Chỉ Là Skeleton

Chưa triển khai:

- OpenAI request thật.
- Backend fetch thật.
- Phân tích xu hướng.
- Xếp hạng rủi ro/cơ hội.
- Tính toán chỉ báo kỹ thuật.
- Phân tích báo cáo tài chính.
- Custom exception framework.
- Lưu lịch sử phân tích vào database.
- Cơ chế auth riêng cho analyse service.

## 15. Hướng Phát Triển Tiếp Theo

Gợi ý thứ tự triển khai:

1. Hoàn thiện `BackendAPIClient` để lấy `stock detail`, `chart`, `watchlist` và `dashboard`.
2. Mở rộng `DataNormalizerService` để xử lý `latest_price`, chart OHLCV, `market_overview`, financials và crawl quality.
3. Hoàn thiện prompt builder cho stock/watchlist/risk.
4. Tích hợp OpenAI SDK với JSON response validation.
5. Bổ sung test schema, prompt và controller.
6. Quyết định endpoint backend còn thiếu cho financial statements, crawl quality và market overview độc lập.

Chất lượng phân tích AI sẽ phụ thuộc trực tiếp vào chất lượng dữ liệu từ crawler và backend. Nếu `latest_price`, `priceHistory`, `financials` hoặc `crawlQuality` thiếu, LLM phải phản ánh điều đó trong phần `dataQuality`.
