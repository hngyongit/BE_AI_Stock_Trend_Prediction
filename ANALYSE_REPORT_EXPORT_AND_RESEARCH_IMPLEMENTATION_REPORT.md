# Báo cáo triển khai xuất file Markdown/HTML và external research cho `analyse`

## 1. Mục tiêu triển khai

Triển khai để endpoint `POST /api/ai-reports/analyse-one` vẫn giữ JSON response shape hiện có, đồng thời tạo file thật:

- `reports/{report_id}.md`
- `reports/{report_id}.html`

Báo cáo Markdown/HTML được dựng bằng tiếng Việt, không hard-code mã ACB/FPT, không để LLM ghi đè số liệu Backend, và có luồng external research/news công khai khi được bật.

## 2. Source code và file mẫu đã đọc

Đã đọc source chính trong `analyse`: `run.py`, `README.md`, `.env.example`, `requirements.txt`, `pyproject.toml`, `src/analyse/main.py`, `app.py`, `api/*`, `clients/*`, `providers/*`, `prompts/*`, `research/*`, `schemas/*`, `services/*`, `utils/*`, `tests/*`, `src/analyse/examples/*`.

Hai file mẫu người dùng nêu:

- `ACB_HOSE_analysis_20260604_100450.md`: Chưa thấy trong source code.
- `ACB_HOSE_financial_report_20260604_100450.html`: Chưa thấy trong source code.

Do không có artifact mẫu trong workspace, phần Markdown/HTML mới bám theo cấu trúc yêu cầu trong prompt và các section bắt buộc.

## 3. Hiện trạng trước khi chỉnh sửa

- `MarkdownService` chỉ tạo placeholder ngắn.
- `HtmlService` chỉ trả metadata/path, chưa sinh HTML thật.
- `ReportService.analyse_one_report()` set `output_path` nhưng không ghi file ra ổ đĩa.
- `VietstockResearchAdapter`, `CafeFResearchAdapter`, `GoogleNewsResearchAdapter` đều trả list rỗng.
- `.env.example` chưa đủ biến điều khiển ghi file/report content/research user-agent/source priority.

## 4. Thay đổi chính đã thực hiện

- Thêm `ReportFileService` để tạo thư mục output và ghi file UTF-8 an toàn.
- Viết lại `MarkdownService.build()` thành báo cáo đầy đủ 0-14 mục bằng tiếng Việt.
- Viết lại `HtmlService.build()` để sinh HTML hoàn chỉnh, responsive, có topbar/sidebar, KPI cards, news cards, appendix và CSS print-friendly.
- Mở rộng schema `ResearchItem` với `positive_flags`, `negative_flags`, `catalyst_flags`.
- Triển khai Google News RSS adapter có cache, timeout, user-agent, parse RSS, lọc relevance và flag keyword.
- Triển khai Vietstock/CafeF bằng Google News RSS có lọc domain `site:vietstock.vn` và `site:cafef.vn`; không scrape trực tiếp.
- Cập nhật `ReportService.analyse_one_report()` để ghi file, trả path thật, thêm warnings khi ghi file/research lỗi.
- Cập nhật README tiếng Việt và test.

## 5. Cách xuất file `.md` và `.html`

`ReportService.analyse_one_report()` dựng `report_id`, gọi:

- `MarkdownService.build(summary, llm_narrative=...)`
- `HtmlService.build(report_id, summary, markdown_content=...)`
- `ReportFileService.write_markdown(report_id, markdown_content)`
- `ReportFileService.write_html(report_id, html_content)`

`ReportFileService.ensure_output_dir()` tạo `REPORT_OUTPUT_DIR` nếu chưa tồn tại. File được ghi bằng UTF-8. `report_id` được sanitize để tránh path traversal.

## 6. Cấu trúc file Markdown mới

`MarkdownService.build()` tạo các mục:

- `# Báo cáo phân tích cổ phiếu {SYMBOL} trên {EXCHANGE}`
- `## 0. Lưu ý và phạm vi`
- `## 1. Kết luận hệ thống: có nên mua không?`
- `## 1A` đến `## 1D`
- `## 2` đến `## 14`

Báo cáo có bảng KPI, bảng coverage, bảng điểm, bảng research/news, phân tích BCTC, định giá, kế hoạch hành động, ma trận kịch bản, checklist và từ điển chỉ số.

## 7. Cấu trúc file HTML mới

`HtmlService.build()` sinh:

- `<!doctype html>`
- `<html lang="vi">`
- UTF-8 meta tag
- topbar/header
- sidebar/table of contents
- các section: `cover`, `executive-summary`, `market-context`, `stock-quality-dashboard`, `financial-statement-analysis`, `peer-comparison`, `external-research`, `investment-memo`, `action-plan`, `strengths`, `weaknesses-risks`, `scenario-matrix`, `checklist`, `metric-dictionary`, `data-coverage`, `appendix`
- KPI cards, news cards, responsive CSS và `@media print`

Mọi text động được escape bằng `html.escape`. URL động được kiểm tra scheme `http/https`; URL không an toàn chuyển thành `#`.

## 8. Cách lấy external research/news

Luồng chính dùng `GoogleNewsResearchAdapter`:

```text
https://news.google.com/rss/search?q={query}&hl=vi&gl=VN&ceid=VN:vi
```

Query được tạo từ symbol, company và các chủ đề như cổ phiếu, kết quả kinh doanh, cổ tức, khuyến nghị. RSS được cache tại `RESEARCH_CACHE_DIR` theo TTL `RESEARCH_CACHE_TTL_SECONDS`.

Vietstock/CafeF adapter hiện dùng Google News RSS có lọc domain. Không bypass paywall, login wall hoặc anti-scraping. Cần kiểm tra thêm nếu muốn tích hợp RSS/search endpoint chính thức riêng của từng nguồn.

## 9. Nguồn tin đã hỗ trợ

- Google News RSS.
- Vietstock qua Google News RSS với `site:vietstock.vn`.
- CafeF qua Google News RSS với `site:cafef.vn`.
- Ưu tiên domain cấu hình: `vietstock.vn`, `cafef.vn`, `tinnhanhchungkhoan.vn`, `vneconomy.vn`, `bnews.vn`.

Nếu Google News không index bài hoặc nguồn chặn truy cập công khai, kết quả có thể trống.

## 10. Cách chấm tone/catalyst/positive/negative flags

Keyword positive:

`tăng trưởng`, `lãi`, `lợi nhuận tăng`, `cổ tức`, `mua ròng`, `nâng khuyến nghị`, `vượt kế hoạch`, `ký hợp đồng`, `mở rộng`, `phục hồi`.

Keyword negative:

`lỗ`, `giảm lợi nhuận`, `nợ`, `xử phạt`, `bán ròng`, `hạ khuyến nghị`, `cảnh báo`, `điều tra`, `rủi ro`, `suy giảm`.

Keyword catalyst:

`cổ tức`, `chia thưởng`, `phát hành`, `niêm yết`, `M&A`, `hợp đồng`, `dự án`, `tăng vốn`, `kết quả kinh doanh`, `đại hội cổ đông`.

Tone là `tích cực`, `tiêu cực`, `hỗn hợp` hoặc `trung tính` dựa trên flags tìm được trong tiêu đề/snippet.

## 11. Cấu hình `.env.example` mới

Đã thêm/hỗ trợ:

```env
REPORT_OUTPUT_DIR=reports
REPORT_WRITE_MARKDOWN=true
REPORT_WRITE_HTML=true
REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE=true
REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false
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
RESEARCH_SOURCE_PRIORITY=vietstock.vn,cafef.vn,tinnhanhchungkhoan.vn,vneconomy.vn,bnews.vn
```

Mọi biến trên đã có field tương ứng trong `Settings`.

## 12. API response sau khi chỉnh

Response vẫn giữ shape cũ. Ví dụ:

```json
{
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
```

Nếu ghi file lỗi, service thêm warning và đánh dấu data source filesystem là `failed`.

## 13. Files đã chỉnh sửa/tạo mới

| File | Thay đổi | Lý do |
|---|---|---|
| `analyse/src/analyse/schemas/common.py` | Cập nhật disclaimer chuẩn | Đúng câu bắt buộc |
| `analyse/src/analyse/config/settings.py` | Thêm report export/research settings | Hỗ trợ `.env.example` mới |
| `analyse/.env.example` | Thêm biến report/research | Hướng dẫn cấu hình runtime |
| `analyse/src/analyse/schemas/research.py` | Thêm flags và source statuses | Chuẩn hóa news/research |
| `analyse/src/analyse/research/base.py` | Thêm keyword/tone/date/domain helpers | Dùng chung cho adapters |
| `analyse/src/analyse/research/google_news.py` | Triển khai Google News RSS, cache, parse RSS | Lấy tin public thật |
| `analyse/src/analyse/research/vietstock.py` | Dùng Google News RSS domain fallback | Hỗ trợ Vietstock không scrape trực tiếp |
| `analyse/src/analyse/research/cafef.py` | Dùng Google News RSS domain fallback | Hỗ trợ CafeF không scrape trực tiếp |
| `analyse/src/analyse/research/research_service.py` | Orchestrate, dedupe, sort, warnings | Không để một nguồn lỗi làm fail report |
| `analyse/src/analyse/services/report_file_service.py` | File service mới | Ghi Markdown/HTML UTF-8 an toàn |
| `analyse/src/analyse/services/markdown_service.py` | Renderer Markdown đầy đủ | Thay placeholder |
| `analyse/src/analyse/services/html_service.py` | Renderer HTML đầy đủ | Thay metadata-only |
| `analyse/src/analyse/services/report_service.py` | Gọi renderer và file writer | Trả path thật, giữ response shape |
| `analyse/tests/test_analyse_one_flow.py` | Cập nhật/add flow tests | Kiểm tra file thật/API data_sources |
| `analyse/tests/test_settings.py` | Test biến env mới | Đảm bảo Settings hỗ trợ |
| `analyse/tests/test_external_research.py` | Test RSS mocked/failure isolation | Không gọi mạng thật trong test |
| `analyse/tests/test_report_file_service.py` | Test ghi file/output dir | Kiểm tra file creation |
| `analyse/tests/test_report_renderers.py` | Test sections/HTML escape | Kiểm tra security/render |
| `analyse/README.md` | Viết lại hướng dẫn tiếng Việt | Hướng dẫn vận hành mới |

## 14. Test đã thêm/chạy

Đã thêm/cập nhật test cho:

- Markdown file creation.
- HTML file creation.
- Output directory creation.
- Google News RSS normalization mocked.
- Vietstock/CafeF domain fallback mocked.
- Research failure không làm fail report.
- HTML escaping và URL không an toàn.
- API/service response có path trỏ tới file thật.
- Settings hỗ trợ biến env mới.

## 15. Kết quả chạy test

Đã chạy:

```powershell
cd analyse
python -m pytest
```

Kết quả:

```text
28 passed in 1.73s
```

## 16. Cách kiểm tra thủ công bằng Postman

Gửi:

```http
POST http://localhost:5100/api/ai-reports/analyse-one
Content-Type: application/json
```

Body:

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

Kiểm tra `data.markdown_report.output_path`, `data.html_report.output_path`, `data.warnings`, `data.data_sources`.

## 17. Cách kiểm tra file đã được tạo trên ổ đĩa

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\analyse
ls reports
start reports\FPT_HOSE_20260622_105312.html
Get-Content reports\FPT_HOSE_20260622_105312.md -Encoding UTF8
```

Tên file thực tế phụ thuộc `report_id` sinh theo symbol, exchange và timestamp hiện tại.

## 18. Rủi ro và giới hạn còn lại

- Hai file mẫu ACB người dùng nêu không có trong workspace: Chưa thấy trong source code.
- Vietstock/CafeF chưa dùng endpoint RSS/search chính thức riêng; hiện là Google News RSS fallback có lọc domain.
- Nếu Google News RSS không trả bài, external research sẽ trống dù source thực tế có bài mới.
- Keyword tone/flags là heuristic đơn giản, không phải phân tích NLP sâu.
- Scoring định lượng trong `ScoringService` vẫn là placeholder an toàn; Cần kiểm tra thêm nếu muốn điểm tài chính/kỹ thuật thực.
- Dữ liệu market/financial phụ thuộc hoàn toàn vào Backend; service không tự bịa số thiếu.

## 19. Kết luận

Endpoint `POST /api/ai-reports/analyse-one` đã tạo được Markdown và HTML report thật, ghi file UTF-8 vào `REPORT_OUTPUT_DIR`, giữ JSON contract hiện có, có external research công khai qua Google News RSS, có cache/warnings/source statuses, và có test tự động xác nhận file creation, HTML escaping, research normalization và response path.
