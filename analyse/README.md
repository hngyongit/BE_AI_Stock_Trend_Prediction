# Analyse Service

**Dự án:** `BE_AI_Stock_Trend_Prediction`  
**Thư mục:** `analyse`  
**Ngôn ngữ tài liệu:** Tiếng Việt  
**Mục tiêu:** Xây dựng service Python/FastAPI dùng AI/LLM để phân tích cổ phiếu, lấy dữ liệu từ Backend, bổ sung dữ liệu nghiên cứu bên ngoài, hỗ trợ 2 provider **Gemini** và **OpenAI**, sau đó trả về JSON report để frontend render HTML/Markdown.

> README này là bản gộp đã làm sạch từ 2 tài liệu: README skeleton hiện tại và báo cáo quy trình phát triển AI Gemini/OpenAI. Các phần trùng lặp về cài đặt, prompt, bảo mật, endpoint, checklist và response schema đã được gom lại để tránh dư thừa.

> Báo cáo phân tích sinh ra từ hệ thống chỉ phục vụ tham khảo/học tập, **không phải khuyến nghị đầu tư cá nhân hóa**.

---

## 1. Mục đích

`analyse` là service Python độc lập cho tầng phân tích AI/LLM của dự án.

Service này có nhiệm vụ:

1. Nhận request phân tích từ frontend/client.
2. Gọi Backend API để lấy watchlist và dữ liệu chi tiết cổ phiếu.
3. Giới hạn mỗi lần phân tích đúng **1 mã cổ phiếu** trong tối đa **5 mã watchlist**.
4. Bổ sung dữ liệu nghiên cứu bên ngoài từ Vietstock, CafeF, Google News/RSS hoặc nguồn public hợp lệ khác.
5. Chuẩn hóa dữ liệu và tính các chỉ số định lượng bằng code.
6. Gọi Gemini hoặc OpenAI để viết phần diễn giải/tóm tắt bằng tiếng Việt.
7. Validate output JSON bằng schema.
8. Trả về response thống nhất cho frontend render HTML/Markdown.

Hiện tại service đang ở trạng thái **skeleton/scaffold**. Một số route, schema và file cấu trúc đã được chuẩn bị, nhưng logic phân tích tài chính, fetch Backend thật, gọi LLM thật, external research thật và render report đầy đủ cần được triển khai tiếp.

---

## 2. Vai trò trong hệ thống

Luồng tổng thể:

```text
crawler → MongoDB → api → analyse → frontend/client
```

| Thành phần | Vai trò |
|---|---|
| `crawler` | Thu thập dữ liệu thị trường, tài chính, nguồn báo cáo, crawl logs và chất lượng crawl. |
| `MongoDB` | Lưu dữ liệu do crawler thu thập. |
| `api` | Backend Node.js/Express/Mongoose, cung cấp REST API cho stock, chart, watchlist, dashboard. |
| `analyse` | Service Python/FastAPI xử lý AI/LLM, chuẩn hóa dữ liệu, tạo summary, Markdown/HTML metadata. |
| `frontend/client` | Gọi analyse service và render report cho người dùng. |

Các route Backend đã xác minh hoặc cần dùng:

| Method | Endpoint | Vai trò | Ghi chú |
|---|---|---|---|
| `GET` | `/api/stocks` | Lấy danh sách cổ phiếu | Trả về `data.items`, `data.pagination`. |
| `GET` | `/api/stocks/:symbol` | Lấy chi tiết 1 mã cổ phiếu | Nguồn định lượng chính cho report. |
| `GET` | `/api/stocks/:symbol/chart?range=1m` | Lấy lịch sử OHLCV | Dùng cho xu hướng/chỉ báo kỹ thuật nếu triển khai. |
| `GET` | `/api/watchlists` | Lấy watchlist user | Yêu cầu Bearer token. |
| `GET` | `/api/dashboard/user` | Lấy dashboard user | Có watchlist, market leaders, market overview. |

Các module như `financials`, `crawl-logs`, `crawl-jobs`, `market-overview`, `markets`, `industries`, `roles`, `data-sources` có thể đã có thư mục trong Backend nhưng cần kiểm tra lại xem đã mount route thật trong `api/src/app.js` chưa trước khi dùng như nguồn API chính thức.

---

## 3. Nguyên tắc thiết kế

| Nguyên tắc | Giải thích |
|---|---|
| Provider-agnostic | Gemini và OpenAI chỉ khác ở tầng gọi model, còn schema, service, frontend response dùng chung. |
| Frontend không gọi trực tiếp LLM | API key phải nằm ở server `.env`, không đưa ra browser. |
| Chỉ phân tích 1 mã/lần | Không phân tích batch 5 mã trong 1 prompt chính để tránh output dài, sai schema và khó kiểm soát. |
| Backend là nguồn định lượng chính | Giá, EPS, P/E, P/B, ROE, doanh thu, lợi nhuận, volume không được để LLM tự bịa. |
| Dữ liệu ngoài chỉ là bổ sung | Vietstock/CafeF/news dùng để thêm ngữ cảnh, không thay thế dữ liệu Backend. |
| Output JSON phải validate được | Mọi kết quả LLM phải parse JSON và validate Pydantic trước khi trả frontend. |
| Luôn có disclaimer | Tránh hiểu nhầm hệ thống là tư vấn đầu tư cá nhân hóa. |
| Thiếu dữ liệu vẫn không crash | Trả `warnings`, `data_quality_notes`, hoặc fallback rule-based. |

---

## 4. Kiến trúc xử lý đề xuất

```text
Frontend
  |
  | POST /api/ai-reports/analyse-one
  v
Analyse Service
  |
  |-- BackendClient
  |     |-- GET /api/watchlists
  |     |-- GET /api/stocks/{symbol}
  |     |-- GET /api/stocks/{symbol}/chart?range=1m
  |
  |-- WatchlistService
  |     |-- Chuẩn hóa symbol
  |     |-- Giới hạn tối đa 5 mã
  |     |-- Kiểm tra symbol request hợp lệ
  |
  |-- ExternalResearchService
  |     |-- Vietstock adapter
  |     |-- CafeF adapter
  |     |-- Google News/RSS adapter
  |     |-- Company IR / public report adapter
  |
  |-- SummaryService / ScoringService
  |     |-- Chuẩn hóa dữ liệu Backend
  |     |-- Tính latest_market, momentum, bctc_3q
  |     |-- Tính scores, system_decision, investment_plan
  |
  |-- LLM Provider Layer
  |     |-- GeminiProvider
  |     |-- OpenAIProvider
  |
  |-- ReportService
  |     |-- Merge dữ liệu định lượng + LLM output
  |     |-- Build Markdown report
  |     |-- Build HTML metadata/path
  |     |-- Validate response schema
  |
  v
JSON Response cho Frontend
```

Luồng dữ liệu cuối cùng:

```text
Backend data
  -> Normalize
  -> Summary
  -> External research
  -> Provider Gemini/OpenAI
  -> Validate JSON
  -> Report response
  -> Frontend HTML
```

---

## 5. Cấu trúc thư mục đề xuất

```text
analyse/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── run.py
├── src/
│   └── analyse/
│       ├── __init__.py
│       ├── main.py
│       ├── app.py
│       ├── api/
│       │   ├── routes.py
│       │   └── dependencies.py
│       ├── clients/
│       │   ├── backend_client.py
│       │   └── http_client.py
│       ├── config/
│       │   └── settings.py
│       ├── providers/
│       │   ├── base.py
│       │   ├── gemini_provider.py
│       │   ├── openai_provider.py
│       │   └── provider_factory.py
│       ├── research/
│       │   ├── base.py
│       │   ├── vietstock.py
│       │   ├── cafef.py
│       │   ├── google_news.py
│       │   └── research_service.py
│       ├── prompts/
│       │   ├── system_prompts.py
│       │   ├── report_prompts.py
│       │   └── json_schema_prompts.py
│       ├── schemas/
│       │   ├── common.py
│       │   ├── watchlist.py
│       │   ├── stock.py
│       │   ├── research.py
│       │   ├── report.py
│       │   └── llm.py
│       ├── services/
│       │   ├── watchlist_service.py
│       │   ├── stock_data_service.py
│       │   ├── summary_service.py
│       │   ├── scoring_service.py
│       │   ├── report_service.py
│       │   ├── markdown_service.py
│       │   └── html_service.py
│       ├── utils/
│       │   ├── datetime_utils.py
│       │   ├── symbol_utils.py
│       │   ├── safe_json.py
│       │   └── logging.py
│       └── examples/
│           ├── sample_stock_request.json
│           ├── sample_watchlist_request.json
│           └── sample_analysis_result.json
└── tests/
    ├── test_backend_client.py
    ├── test_provider_factory.py
    ├── test_report_schema.py
    └── test_analyse_one_flow.py
```

| Thư mục/file | Vai trò |
|---|---|
| `api` | Khai báo FastAPI routes/controllers. |
| `clients` | Gọi Backend API và HTTP helper. |
| `config` | Đọc biến môi trường bằng Pydantic settings/dotenv. |
| `providers` | Tầng gọi Gemini/OpenAI dùng chung interface. |
| `research` | Adapter lấy dữ liệu ngoài từ Vietstock/CafeF/Google News. |
| `prompts` | Prompt hệ thống, prompt report, prompt JSON schema. |
| `schemas` | Pydantic request/response models. |
| `services` | Business logic: watchlist, stock data, scoring, report, markdown, html. |
| `utils` | Helper xử lý datetime, symbol, safe JSON, logging. |
| `examples` | Request/response mẫu bằng tiếng Việt. |
| `tests` | Unit/integration tests. |

---

## 6. Công nghệ sử dụng

- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic
- pydantic-settings
- python-dotenv
- httpx
- OpenAI Python SDK
- Google Gemini SDK hoặc HTTP client tương ứng
- pytest

---

## 7. Cài đặt local

Dự án sử dụng `uv` để quản lý môi trường Python và cài đặt dependencies.

### Windows PowerShell

```powershell
cd analyse
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
copy .env.example .env
uv run python run.py
```

Bash/macOS/Linux:

```bash
cd analyse
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
uv run python run.py
```

Service mặc định chạy tại:

```text
http://localhost:5100
```

Swagger UI:

```text
http://localhost:5100/api/analyse/docs
```

---

## 8. Biến môi trường

### 8.1. Cấu hình chung

```env
ANALYSE_ENV=development
ANALYSE_HOST=0.0.0.0
ANALYSE_PORT=5100
ANALYSE_LOG_LEVEL=INFO
ANALYSE_TIMEZONE=Asia/Ho_Chi_Minh
PYTHONPATH=src

BACKEND_API_BASE_URL=http://localhost:5000
BACKEND_API_TIMEOUT_MS=30000
BACKEND_API_TOKEN=
BACKEND_WATCHLIST_ENDPOINT=/api/watchlists
BACKEND_STOCK_DETAIL_ENDPOINT=/api/stocks/{symbol}
BACKEND_STOCK_CHART_ENDPOINT=/api/stocks/{symbol}/chart?range={range}

REPORT_OUTPUT_DIR=reports
REPORT_LANGUAGE=vi
SUMMARY_SCHEMA_VERSION=1.0
MAX_WATCHLIST_SYMBOLS=5
ANALYSE_ONE_SYMBOL_ONLY=true

ENABLE_EXTERNAL_RESEARCH=true
ENABLE_VIETSTOCK=true
ENABLE_CAFEF=true
ENABLE_GOOGLE_NEWS_RSS=true
RESEARCH_CACHE_DIR=.research_cache
RESEARCH_CACHE_TTL_SECONDS=21600
RESEARCH_TIMEOUT_MS=20000
MAX_RESEARCH_ITEMS=10

DEFAULT_CAPITAL_VND=100000000
DEFAULT_RISK_PER_TRADE_PCT=1.0
DEFAULT_MAX_POSITION_PCT=12.0
```

### 8.2. Cấu hình Gemini

```env
GEMINI_ENABLED=true
GEMINI_API_KEY=
GEMINI_MODEL=gemini-model-configurable
GEMINI_TEMPERATURE=0.2
GEMINI_TOP_P=0.9
GEMINI_MAX_OUTPUT_TOKENS=8192
GEMINI_TIMEOUT_MS=60000
GEMINI_JSON_MODE=true
```

### 8.3. Cấu hình OpenAI

```env
OPENAI_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=openai-model-configurable
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_OUTPUT_TOKENS=8192
OPENAI_TIMEOUT_MS=60000
OPENAI_JSON_MODE=true
```

Lưu ý:

- Không hard-code model trong source code.
- Không commit `.env`.
- Không log `OPENAI_API_KEY`, `GEMINI_API_KEY`, `BACKEND_API_TOKEN`.
- Skeleton có thể chạy không cần API key thật nếu các provider vẫn là placeholder/mock.

---

## 9. API endpoints

### 9.1. Endpoint hiện có trong skeleton

| Method | Endpoint | Trạng thái | Mục đích |
|---|---|---|---|
| `GET` | `/` | Placeholder | Root/health đơn giản. |
| `GET` | `/api/analyse/health` | Placeholder | Health check. |
| `POST` | `/api/analyse/stock` | Placeholder | Nhận dữ liệu trực tiếp, trả phân tích mẫu. |
| `POST` | `/api/analyse/watchlist` | Placeholder | Nhận watchlist, trả kế hoạch theo dõi mẫu. |
| `POST` | `/api/analyse/fetch-and-analyse/stock` | Placeholder | Khai báo fetch mode, chưa gọi Backend thật. |

### 9.2. Endpoint mục tiêu cho report HTML/Markdown

Endpoint chính nên triển khai:

```http
POST /api/ai-reports/analyse-one
```

Mục tiêu:

- Chỉ phân tích 1 mã.
- Kiểm tra mã có nằm trong tối đa 5 mã watchlist hợp lệ.
- Gọi `/api/watchlists`.
- Gọi `/api/stocks/:symbol`.
- Lấy research ngoài nếu bật.
- Gọi Gemini hoặc OpenAI tùy request.
- Trả JSON chuẩn cho frontend.

Endpoint đọc lại report sau này nếu có lưu metadata/database:

```http
GET /api/ai-reports/{report_id}
```

---

## 10. Request tạo report

```json
{
  "provider": "openai",
  "symbol": "FPT",
  "scope_exchange": "HOSE",
  "options": {
    "language": "vi",
    "include_external_research": true,
    "render_markdown": true,
    "render_html": true,
    "capital_vnd": 100000000,
    "risk_per_trade_pct": 1.0,
    "max_position_pct": 12.0
  }
}
```

| Field | Type | Required | Mô tả |
|---|---|---:|---|
| `provider` | string | Có | `gemini` hoặc `openai`. |
| `symbol` | string | Có | Mã cổ phiếu cần phân tích. |
| `scope_exchange` | string | Không | Mặc định `HOSE`. |
| `options.language` | string | Không | Mặc định `vi`. |
| `options.include_external_research` | boolean | Không | Có lấy tin ngoài không. |
| `options.render_markdown` | boolean | Không | Có tạo Markdown report không. |
| `options.render_html` | boolean | Không | Có tạo HTML report không. |
| `options.capital_vnd` | number | Không | Vốn tham chiếu để tính position sizing. |
| `options.risk_per_trade_pct` | number | Không | Rủi ro mỗi lệnh. |
| `options.max_position_pct` | number | Không | Tỷ trọng tối đa tham chiếu. |

---

## 11. Quy tắc watchlist và one-symbol-only

Mỗi request chỉ được phân tích **1 mã cổ phiếu** trong tối đa **5 mã watchlist**.

Không làm:

```json
{
  "provider": "openai",
  "symbols": ["FPT", "CMG", "MWG", "HPG", "VCB"]
}
```

Logic xử lý:

| Bước | Logic |
|---:|---|
| 1 | Gọi `GET /api/watchlists`. |
| 2 | Chuẩn hóa symbol: uppercase, trim, bỏ duplicate. |
| 3 | Lấy tối đa `MAX_WATCHLIST_SYMBOLS=5`. |
| 4 | Kiểm tra `request.symbol` có nằm trong 5 mã này không. |
| 5 | Nếu không nằm trong danh sách, trả lỗi `SYMBOL_NOT_IN_WATCHLIST`. |
| 6 | Nếu hợp lệ, chỉ gọi `GET /api/stocks/{symbol}` cho đúng 1 mã. |
| 7 | Không đưa dữ liệu 4 mã còn lại vào prompt chính, trừ khi chỉ dùng làm context ngắn. |

Pseudo-code:

```python
watchlists = await backend_client.get_watchlists()
symbols = normalize_symbols(watchlists)
allowed_symbols = symbols[:settings.MAX_WATCHLIST_SYMBOLS]

if request.symbol not in allowed_symbols:
    raise SymbolNotInWatchlistError()

stock_detail = await backend_client.get_stock_detail(symbol=request.symbol)
```

---

## 12. External research

Nguồn nên hỗ trợ:

| Nguồn | Loại | Dùng để | Trạng thái |
|---|---|---|---|
| Vietstock | `public_html` | Hồ sơ doanh nghiệp, dữ liệu thị trường, tin liên quan | Có thể bật/tắt |
| CafeF | `public_html` hoặc `rss` | Tin doanh nghiệp, tài chính, sự kiện | Có thể bật/tắt |
| Google News RSS | `rss` | Tổng hợp tin mới theo mã và tên công ty | Có thể bật/tắt |
| Website doanh nghiệp | `investor_relations` | Báo cáo thường niên, nghị quyết, BCTC | Optional |
| Công ty chứng khoán | `research_pdf/html` | Báo cáo phân tích public | Optional |

Schema item nghiên cứu:

```json
{
  "source": "CafeF",
  "type": "public_html",
  "title": "FPT công bố kết quả kinh doanh...",
  "url": "https://...",
  "published_at": "2026-06-18T09:00:00+07:00",
  "snippet": "Tóm tắt ngắn...",
  "tone": "positive",
  "relevance_score": 0.82,
  "status": "success"
}
```

Quy tắc:

| Quy tắc | Giải thích |
|---|---|
| Có source rõ ràng | Mỗi item nên có `source`, `url`, `published_at` nếu lấy được. |
| Không coi tin ngoài là số liệu gốc | Số liệu giá/tài chính vẫn lấy từ Backend. |
| Có cache | Tránh gọi nguồn public quá nhiều. |
| Có status | `success`, `partial`, `failed`, `disabled`. |
| Có warning | Nếu không lấy được tin, report vẫn chạy nhưng thêm cảnh báo. |
| Không bypass login/anti-bot | Chỉ dùng dữ liệu public hợp lệ. |

Context đưa vào summary:

```json
{
  "enabled": true,
  "status": "success",
  "items": [],
  "flag_summary": {
    "positive_flags": {},
    "negative_flags": {},
    "catalysts": {},
    "average_tone_score": null
  },
  "note": "Dữ liệu nghiên cứu bên ngoài chỉ dùng để tham khảo, cần kiểm chứng lại trước khi ra quyết định."
}
```

---

## 13. Summary và scoring

Không để LLM tự tính các chỉ số quan trọng nếu có thể tính bằng code.

Nên tính bằng code:

| Nhóm | Field |
|---|---|
| Giá/thị trường | `latest_market.price`, `volume`, `market_cap_bil_vnd`, `pe`, `pb`, `eps`, `roe_pct`, `beta`. |
| Thanh khoản | `avg_volume_1m`, `liquidity_vs_1m_pct`. |
| Momentum | `change_1w_pct`, `change_1m_pct`, `change_1q_pct`, `pct_from_52w_high`, `pct_above_52w_low`. |
| Tài chính | `bctc_3q`, `gross_margin_3q_pct`, `net_margin_3q_pct`, `debt_to_equity_x`. |
| Điểm số | `valuation_score`, `quality_score`, `growth_score`, `momentum_score`, `risk_score`, `overall_score`. |
| Quyết định hệ thống | `system_decision.status`, `reasons`, `blockers`. |
| Kế hoạch | `investment_plan.reference_levels`, `position_sizing`, `action_table`. |

LLM chỉ nên hỗ trợ:

| Phần | LLM được sinh? | Ghi chú |
|---|---:|---|
| `summary.strengths` | Có | Dựa trên số liệu đã có. |
| `summary.weaknesses` | Có | Dựa trên số liệu, warning, tin ngoài. |
| `summary.system_decision.reasons` | Có một phần | Decision chính nên có rule kiểm soát. |
| `markdown_report.content` | Có | Dùng để viết báo cáo tiếng Việt dễ đọc. |
| `latest_market.price` | Không | Lấy từ Backend. |
| `scores.overall_score` | Không nên | Nên tính bằng code. |
| `investment_plan.reference_levels` | Không nên | Nên tính bằng code. |

Field `summary` tối thiểu:

| Nhóm field | Field | Mục đích |
|---|---|---|
| Thông tin chung | `symbol`, `company`, `scope_exchange`, `disclaimer` | Hiển thị phần đầu report. |
| Độ phủ dữ liệu | `data_coverage` | Cho biết dữ liệu đủ hay thiếu. |
| Thị trường mới nhất | `latest_market` | Giá, thanh khoản, P/E, P/B, EPS, ROE, beta. |
| Momentum | `momentum` | Biến động 1W/1M/1Q/1Y, 52W high/low. |
| BCTC | `bctc_3q` | Doanh thu, lợi nhuận, EPS, margin, QoQ. |
| Cân đối tài chính | `financial_balance` | Tài sản, nợ, vốn chủ, debt ratio. |
| Bối cảnh thị trường | `hose_market_context` | VNINDEX, breadth, regime. |
| Điểm số | `scores` | Valuation, quality, growth, momentum, risk, overall. |
| Điểm mạnh/yếu | `strengths`, `weaknesses` | Bullet point cho report. |
| Peer cùng ngành | `industry_peer_context` | So sánh ngành. |
| Research ngoài | `external_research_context` | Tin tức/bài báo. |
| Quyết định hệ thống | `system_decision` | Trạng thái, action, blocker. |
| Kế hoạch đầu tư | `investment_plan` | Vùng giá, sizing, action table. |
| Cảnh báo | `warnings` | Thiếu dữ liệu, lỗi research, fallback LLM. |

---

## 14. LLM Provider Layer

Interface dùng chung:

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseLLMProvider(ABC):
    provider_name: str

    @abstractmethod
    async def generate_report_json(
        self,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Nhận context đã chuẩn hóa và trả về JSON đã parse."""
        raise NotImplementedError
```

Provider factory:

```python
def get_llm_provider(provider: str) -> BaseLLMProvider:
    if provider == "gemini":
        return GeminiProvider()
    if provider == "openai":
        return OpenAIProvider()
    raise ValueError(f"Unsupported provider: {provider}")
```

So sánh Gemini và OpenAI:

| Tiêu chí | Gemini | OpenAI | Quy tắc chung |
|---|---|---|---|
| API key | `GEMINI_API_KEY` | `OPENAI_API_KEY` | Đều nằm trong `.env` server. |
| Model | `GEMINI_MODEL` | `OPENAI_MODEL` | Không hard-code. |
| Provider class | `GeminiProvider` | `OpenAIProvider` | Cùng implement `BaseLLMProvider`. |
| File | `providers/gemini_provider.py` | `providers/openai_provider.py` | Tách riêng để dễ bảo trì. |
| Output | JSON report | JSON report | Cùng schema, frontend không cần đổi. |
| Prompt | Có thể tối ưu riêng | Có thể tối ưu riêng | Cùng policy: không bịa số liệu. |
| Fallback | Rule-based/OpenAI nếu cho phép | Rule-based/Gemini nếu cho phép | Tùy config. |
| Validate | Pydantic | Pydantic | Bắt buộc. |

Prompt nguyên tắc áp dụng chung:

```text
Bạn là AI phân tích cổ phiếu bằng tiếng Việt.

Yêu cầu bắt buộc:
1. Chỉ dùng dữ liệu trong JSON CONTEXT.
2. Không bịa dữ liệu tài chính.
3. Nếu số liệu thiếu, ghi null hoặc thêm warning/data_quality_notes.
4. Không đảm bảo lợi nhuận.
5. Không đưa lời khuyên đầu tư cá nhân hóa.
6. Không đưa lệnh mua/bán tuyệt đối.
7. Output chỉ là JSON hợp lệ.
8. Không thêm markdown, code fence hoặc bình luận ngoài JSON.

JSON CONTEXT:
{...}

RESPONSE JSON SCHEMA:
{...}
```

Validate output LLM:

1. Parse JSON.
2. Validate bằng Pydantic schema.
3. Kiểm tra field bắt buộc.
4. So sánh số liệu định lượng với dữ liệu gốc.
5. Nếu LLM đổi giá, P/E, EPS, score hoặc vùng giá, dùng dữ liệu code ghi đè lại.
6. Nếu JSON lỗi, thử repair JSON nếu có module riêng.
7. Nếu vẫn lỗi, fallback rule-based hoặc trả `LLM_UNAVAILABLE`.

---

## 15. Response JSON chuẩn cho frontend

Response phải giữ khung chính:

```json
{
  "code": 200,
  "message": "Tạo dữ liệu report thành công",
  "data": {
    "report_id": "FPT_HOSE_20260618_103000",
    "generated_at": "2026-06-18T10:30:00+07:00",
    "symbol": "FPT",
    "company": "FPT Corp",
    "scope_exchange": "HOSE",
    "language": "vi",
    "summary_schema_version": "1.0",
    "provider": {
      "name": "openai",
      "model": "openai-model-configurable",
      "status": "success",
      "latency_ms": 0
    },
    "data_sources": [
      {"name": "Backend /api/watchlists", "type": "backend_api", "status": "success"},
      {"name": "Backend /api/stocks/:symbol", "type": "backend_api", "status": "success"},
      {"name": "Vietstock", "type": "public_html", "status": "success"},
      {"name": "CafeF", "type": "public_html", "status": "partial"},
      {"name": "Google News RSS", "type": "rss", "status": "success"}
    ],
    "summary": {},
    "markdown_report": {
      "available": true,
      "output_path": "reports/FPT_HOSE_analysis_20260618_103000.md",
      "content": "# Báo cáo phân tích cổ phiếu FPT trên HoSE\n\n..."
    },
    "html_report": {
      "available": true,
      "output_path": "reports/FPT_HOSE_financial_report_20260618_103000.html",
      "content": null,
      "template_name": "src/analyse/services/html_service.py::render_html_report"
    },
    "warnings": []
  }
}
```

Field `data` cấp cao:

| Field | Type | Required | Dùng cho HTML | Mô tả |
|---|---|---:|---:|---|
| `report_id` | string | Có | Có | ID report duy nhất. |
| `generated_at` | datetime string | Có | Có | Thời điểm tạo report. |
| `symbol` | string | Có | Có | Mã cổ phiếu. |
| `company` | string/null | Không | Có | Tên công ty. |
| `scope_exchange` | string | Có | Có | Sàn/phạm vi. |
| `language` | string | Có | Có | Ngôn ngữ report. |
| `summary_schema_version` | string | Có | Không | Version schema. |
| `provider` | object | Có | Có thể | AI provider đã dùng. |
| `data_sources` | array | Có | Có | Trạng thái nguồn dữ liệu. |
| `summary` | object | Có | Có | Dữ liệu lõi render report. |
| `markdown_report` | object | Có | Phụ lục | Nội dung/path markdown. |
| `html_report` | object | Có | Có | Nội dung/path html. |
| `warnings` | array | Có | Có | Cảnh báo. |

---

## 16. Mapping field sang HTML

| HTML Section | Field dùng chính | Ghi chú |
|---|---|---|
| Cover/Hero | `symbol`, `company`, `scope_exchange`, `generated_at`, `scores`, `system_decision` | Hiển thị headline. |
| Tóm tắt điều hành | `system_decision`, `latest_market`, `scores` | Phần quan trọng nhất. |
| Bối cảnh thị trường | `hose_market_context`, `market_general_context` | VNINDEX, breadth, market stance. |
| Dashboard cổ phiếu | `latest_market`, `momentum`, `scores`, `ranks_in_hose` | KPI chính. |
| Phân tích BCTC | `bctc_3q`, `financial_balance` | Kết quả kinh doanh, margin. |
| So sánh cùng ngành | `industry_peer_context`, `same_industry_recommendation` | Peer table. |
| Tin tức bên ngoài | `external_research_context.items` | Vietstock/CafeF/news. |
| Investment memo | `scores`, `strengths`, `weaknesses`, `system_decision` | Luận điểm đầu tư. |
| Kế hoạch hành động | `investment_plan.reference_levels`, `position_sizing`, `action_table` | Vùng mua/bán tham chiếu. |
| Rủi ro | `weaknesses`, `system_decision.blockers`, `warnings` | Risk cards. |
| Phụ lục Markdown | `markdown_report.content` | Hiển thị report dạng text. |

---

## 17. Error response chuẩn

```json
{
  "code": 400,
  "message": "Không thể tạo report",
  "error": {
    "type": "VALIDATION_ERROR",
    "details": [
      {
        "field": "symbol",
        "message": "symbol là bắt buộc"
      }
    ]
  },
  "data": null
}
```

| HTTP/code | `error.type` | Khi nào |
|---:|---|---|
| 400 | `VALIDATION_ERROR` | Thiếu symbol, provider sai, options sai kiểu. |
| 400 | `ONE_SYMBOL_ONLY` | Request truyền nhiều mã. |
| 403 | `SYMBOL_NOT_IN_WATCHLIST` | Symbol không nằm trong 5 mã watchlist hợp lệ. |
| 404 | `SYMBOL_NOT_FOUND` | `/api/stocks/:symbol` không có dữ liệu. |
| 422 | `DATA_SOURCE_ERROR` | Backend trả dữ liệu thiếu nghiêm trọng. |
| 424 | `EXTERNAL_RESEARCH_ERROR` | Chỉ dùng khi strict mode bật. |
| 500 | `REPORT_GENERATION_ERROR` | Lỗi tính summary/render. |
| 503 | `LLM_UNAVAILABLE` | Gemini/OpenAI lỗi và không có fallback. |

---

## 18. Ví dụ chạy API local

Health check:

```bash
curl http://localhost:5100/api/analyse/health
```

Test skeleton stock placeholder:

```bash
curl -X POST http://localhost:5100/api/analyse/stock \
  -H "Content-Type: application/json" \
  -d @src/analyse/examples/sample_stock_request.json
```

PowerShell:

```powershell
curl.exe -X POST http://localhost:5100/api/analyse/stock `
  -H "Content-Type: application/json" `
  -d "@src/analyse/examples/sample_stock_request.json"
```

Test endpoint mục tiêu:

```powershell
curl -X POST http://localhost:5100/api/ai-reports/analyse-one ^
  -H "Content-Type: application/json" ^
  -d "{\"provider\":\"openai\",\"symbol\":\"FPT\",\"options\":{\"include_external_research\":true}}"
```

---

## 19. Kiểm thử

Chạy test:

```powershell
python -m pytest
```

Các nhóm test cần có:

| Test | Mục tiêu |
|---|---|
| `test_backend_client.py` | Gọi đúng `/api/watchlists`, `/api/stocks/:symbol`, xử lý timeout/error. |
| `test_provider_factory.py` | Chọn đúng Gemini/OpenAI, reject provider sai. |
| `test_report_schema.py` | Response đúng schema `code/message/data`. |
| `test_analyse_one_flow.py` | Chỉ phân tích 1 mã, giới hạn 5 mã watchlist. |
| Research fallback test | Research lỗi không làm chết report. |
| No secret leakage test | Không trả API key/token ra response hoặc log. |

---

## 20. Checklist phát triển

| Giai đoạn | Việc cần làm | Kết quả |
|---|---|---|
| 1. Chuẩn bị | Tạo folder `analyse`, `.env.example`, `requirements.txt`, `run.py`, `README.md` | Có module AI độc lập và chạy được skeleton. |
| 2. Backend | Tạo `BackendClient`, `get_watchlists()`, `get_stock_detail(symbol)`, chart fetch nếu cần | Gọi được dữ liệu từ Backend. |
| 3. Watchlist | Chuẩn hóa symbol, giới hạn 5 mã, chặn batch analysis | Đúng yêu cầu nghiệp vụ. |
| 4. Research | Tạo adapter Vietstock, CafeF, Google News RSS, cache/TTL | Có ngữ cảnh ngoài nhưng không làm chết report khi lỗi. |
| 5. Summary | Map stock detail, tính `latest_market`, `momentum`, `bctc_3q`, `scores`, `investment_plan` | Có dữ liệu định lượng sạch. |
| 6. Provider | Tạo `BaseLLMProvider`, `GeminiProvider`, `OpenAIProvider`, `ProviderFactory` | Chọn provider bằng request. |
| 7. API route | Tạo `POST /api/ai-reports/analyse-one`, request/response schema, error handler | Frontend gọi được. |
| 8. Render | Tạo Markdown, HTML output path, ghi file vào `reports/` | Frontend đủ dữ liệu hiển thị. |
| 9. Test | Test provider, watchlist limit, one-symbol-only, backend client, schema, security | Test chính pass. |

---

## 21. Checklist bảo mật

| Checklist | Bắt buộc |
|---|---:|
| Không commit `.env` | Có |
| Không commit API key | Có |
| Không log `OPENAI_API_KEY` | Có |
| Không log `GEMINI_API_KEY` | Có |
| Không log `BACKEND_API_TOKEN` | Có |
| Không trả secret qua API | Có |
| Không để frontend gọi LLM trực tiếp | Có |
| Có timeout cho Backend/external research | Có |
| Có cache và rate limit cho external research | Nên có |
| Có disclaimer trong report | Có |
| Không bypass login/anti-bot của nguồn public | Có |

---

## 22. Những phần còn là skeleton hoặc cần triển khai tiếp

- Gọi OpenAI thật.
- Gọi Gemini thật.
- Backend fetch thật từ `/api/watchlists`, `/api/stocks/:symbol`, chart.
- Phân tích xu hướng định lượng.
- Xếp hạng rủi ro/cơ hội.
- Tính chỉ báo kỹ thuật như RSI, MACD, MA20/MA50/MA200.
- Phân tích báo cáo tài chính đầy đủ.
- External research thật từ Vietstock/CafeF/Google News.
- Custom exception framework.
- Lưu lịch sử phân tích vào database.
- Cơ chế auth riêng cho analyse service.
- Render HTML thực tế hoặc serve static file report.
- Kiểm thử tích hợp end-to-end.

---

## 23. Definition of Done

Tính năng được xem là hoàn thành khi:

| Mục | Đạt khi |
|---|---|
| Gemini config | `.env` có đủ biến Gemini, provider chạy được. |
| OpenAI config | `.env` có đủ biến OpenAI, provider chạy được. |
| Backend watchlist | Gọi được `/api/watchlists`. |
| Backend stock detail | Gọi được `/api/stocks/:symbol`. |
| One-symbol rule | Không phân tích nhiều mã một lần. |
| Watchlist limit | Chỉ xét tối đa 5 mã. |
| External research | Có Vietstock/CafeF/news context hoặc fallback rõ ràng. |
| Summary schema | Có `latest_market`, `momentum`, `bctc_3q`, `scores`, `system_decision`, `investment_plan`. |
| JSON response | Frontend nhận đúng `code/message/data`. |
| Markdown report | Có `markdown_report.available=true` nếu bật. |
| HTML report | Có `html_report.available=true` nếu bật. |
| Warning | Thiếu dữ liệu không làm hệ thống crash. |
| Tests | Test chính pass. |
| Security | Không có secret trong log/response/source control. |

---

## 24. Hướng phát triển tiếp theo

Thứ tự triển khai nên làm:

1. Hoàn thiện `BackendClient` để lấy `watchlists`, `stock detail`, `chart` và `dashboard`.
2. Mở rộng `DataNormalizerService` để xử lý `latest_price`, OHLCV, `market_overview`, financials và crawl quality.
3. Hoàn thiện `WatchlistService` để enforce `MAX_WATCHLIST_SYMBOLS=5` và one-symbol-only.
4. Tạo `ExternalResearchService` với cache, timeout, status và warning.
5. Tạo `SummaryService` và `ScoringService` để tính số liệu bằng code.
6. Tạo `BaseLLMProvider`, `GeminiProvider`, `OpenAIProvider`, `ProviderFactory`.
7. Hoàn thiện prompt builder và JSON schema prompt.
8. Tạo `POST /api/ai-reports/analyse-one`.
9. Tạo `ReportService` để build response, Markdown, HTML metadata.
10. Viết test đầy đủ cho BackendClient, provider, schema, flow, security.
11. Cập nhật frontend để gọi endpoint mới và render theo `data.summary`.

---

## 25. Kết luận

`analyse` nên được phát triển như một service AI độc lập, có cấu trúc rõ ràng và không phụ thuộc vào một provider duy nhất. Gemini và OpenAI chỉ nên là hai implementation của cùng một interface. Toàn bộ phần dữ liệu, summary, scoring, validation, response schema và HTML/Markdown mapping phải dùng chung để frontend không cần đổi logic khi đổi provider.

Điểm quan trọng nhất là **không để LLM quyết định toàn bộ hệ thống**. Các số liệu như giá, P/E, P/B, ROE, EPS, doanh thu, lợi nhuận, điểm số, vùng giá và position sizing nên được tính bằng code từ dữ liệu Backend. LLM chỉ nên giúp diễn giải, tóm tắt, viết báo cáo tiếng Việt dễ hiểu và bổ sung nhận định dựa trên dữ liệu đã được cung cấp.

Nếu làm đúng kiến trúc này, hệ thống sẽ có luồng ổn định:

```text
Backend data
  -> Normalize
  -> Quant summary
  -> External research
  -> Gemini/OpenAI narrative
  -> Validate JSON
  -> Markdown/HTML report
  -> Frontend render
```
