# Dịch vụ `analyse`

`analyse` là dịch vụ Python/FastAPI dùng để tạo báo cáo phân tích cổ phiếu Việt Nam bằng LLM. Thư mục này đã được hợp nhất từ hai hướng triển khai `analyse-gemini` và `analyse-openai` theo cùng một hợp đồng API, cùng request/response schema và cùng luồng xử lý nghiệp vụ.

Báo cáo chỉ phục vụ tham khảo/học tập, không phải khuyến nghị đầu tư cá nhân hóa.

## 1. Mục đích

Dịch vụ nhận một mã cổ phiếu, lấy dữ liệu định lượng từ Backend API, tạo summary/scoring bằng code, gọi OpenAI hoặc Gemini để viết phần diễn giải tiếng Việt, sau đó trả về một response thống nhất cho frontend.

Provider chỉ được khác nhau ở bước gọi model và parse output. Các phần còn lại dùng chung:

- endpoint chính;
- request schema;
- response schema;
- Backend API flow;
- summary/scoring/report flow;
- Markdown/HTML metadata;
- provider metadata;
- cấu hình `.env.example`;
- test style.

## 2. Endpoint chính

```http
POST /api/ai-reports/analyse-one
```

Các route cũ dưới `/api/analyse/*` vẫn tồn tại cho tương thích skeleton, nhưng endpoint tạo report chính là `/api/ai-reports/analyse-one`.

## 3. Cài đặt

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

## 4. Cấu hình `.env`

Sao chép `.env.example` thành `.env` và điền các biến cần thiết.

Nhóm biến quan trọng:

```env
BACKEND_API_BASE_URL=http://localhost:5000
BACKEND_API_TOKEN=

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

## 5. Chọn OpenAI, Gemini và model

Có ba cách chọn provider/model:

1. Truyền `provider: "openai"` hoặc `provider: "gemini"` trong request.
2. Nếu không truyền `provider`, service dùng `DEFAULT_LLM_PROVIDER`.
3. Nếu truyền `model` và `ALLOW_REQUEST_MODEL_OVERRIDE=true`, service dùng model trong request cho lần gọi đó.

Nếu request không truyền `model`:

- provider `openai` dùng `OPENAI_MODEL`;
- provider `gemini` dùng `GEMINI_MODEL`.

Nếu `ALLOW_REQUEST_MODEL_OVERRIDE=false`, model trong request bị bỏ qua và response thêm warning.

## 6. Request mẫu

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

Alias camelCase được hỗ trợ cho `scopeExchange` và các field trong `options`.

## 7. Response mẫu

```json
{
  "code": 200,
  "message": "Tạo dữ liệu report thành công",
  "data": {
    "report_id": "FPT_HOSE_20260622_153000",
    "generated_at": "2026-06-22T15:30:00+07:00",
    "symbol": "FPT",
    "company": "Công ty Cổ phần FPT",
    "scope_exchange": "HOSE",
    "language": "vi",
    "summary_schema_version": "1.0",
    "provider": {
      "name": "openai",
      "model": "gpt-4.1-mini",
      "status": "success",
      "latency_ms": 1200
    },
    "data_sources": [],
    "summary": {},
    "markdown_report": {
      "available": true,
      "output_path": "reports/FPT_HOSE_20260622_153000.md",
      "content": "# Báo cáo phân tích cổ phiếu FPT..."
    },
    "html_report": {
      "available": true,
      "output_path": "reports/FPT_HOSE_20260622_153000.html",
      "content": null,
      "template_name": "src/analyse/services/html_service.py::build_metadata"
    },
    "warnings": []
  }
}
```

OpenAI và Gemini trả cùng response shape. Frontend chỉ cần đọc `data.provider.name` để biết provider đã dùng.

## 8. Backend API yêu cầu

`analyse` không hard-code URL Backend. Các endpoint được cấu hình qua `.env`:

```env
BACKEND_WATCHLIST_ENDPOINT=/api/watchlists
BACKEND_STOCK_DETAIL_ENDPOINT=/api/stocks/{symbol}
BACKEND_STOCK_CHART_ENDPOINT=/api/stocks/{symbol}/chart?range={range}
```

Luồng xử lý:

1. Gọi `GET /api/watchlists`.
2. Chuẩn hóa symbol và chỉ lấy tối đa `MAX_WATCHLIST_SYMBOLS`.
3. Nếu `ANALYSE_ONE_SYMBOL_ONLY=true`, chỉ cho phân tích symbol nằm trong 5 mã đầu.
4. Gọi `GET /api/stocks/{symbol}`.
5. Gọi `GET /api/stocks/{symbol}/chart?range={range}` để bổ sung `price_history` và momentum đơn giản.
6. Nếu bật external research, gọi các adapter Vietstock, CafeF, Google News RSS.
7. Tạo summary/scoring bằng code.
8. Gọi provider LLM đã chọn.
9. Merge output LLM vào summary/Markdown theo whitelist.

## 9. Chiến lược merge output LLM

LLM chỉ được đóng góp các field diễn giải:

- `strengths`;
- `weaknesses`;
- `system_decision.reasons`;
- `markdown_report.content`;
- `data_quality_notes`.

Service không nhận các field định lượng từ LLM. Các field sau luôn giữ từ Backend/code:

- giá, volume, EPS, P/E, P/B, ROE;
- financial ratios;
- scores;
- vùng giá tham chiếu;
- position sizing;
- dữ liệu Backend thô.

Khi LLM lỗi, bị tắt hoặc thiếu API key, service vẫn giữ deterministic summary và dùng Markdown rule-based fallback.

## 10. Chạy test

```powershell
cd analyse
python -m pytest
```

Hoặc:

```powershell
cd analyse
uv run pytest
```

## 11. Giới hạn hiện tại

- External research adapters hiện vẫn là placeholder an toàn, chưa crawl dữ liệu thật.
- HTML report mới trả metadata/path, chưa render file HTML hoàn chỉnh.
- Scoring định lượng còn là placeholder an toàn, cần bổ sung công thức tài chính/kỹ thuật đầy đủ.
- Route `/api/analyse/*` vẫn là route tương thích skeleton, không phải luồng report chính.
- Backend `/api/watchlists` yêu cầu Bearer token nếu Backend bật auth; cần cấu hình `BACKEND_API_TOKEN`.
