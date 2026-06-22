# Báo cáo sửa lỗi xuất HTML report cho `analyse`

## 1. Vấn đề ban đầu

API `POST /api/ai-reports/analyse-one` tạo được Markdown file:

```json
"markdown_report": {
  "available": true,
  "output_path": "reports/FPT_HOSE_20260622_125159.md"
}
```

Nhưng HTML report bị để trống:

```json
"html_report": {
  "available": false,
  "output_path": null,
  "content": null,
  "template_name": null
}
```

## 2. Nguyên nhân gốc rễ

Đã kiểm tra alias `renderHtml -> render_html` bằng Pydantic: body mẫu với `"renderHtml": true` parse đúng thành `request.options.render_html is True`.

Đã kiểm tra `.env.example` và `Settings`: `REPORT_WRITE_HTML` đã tồn tại, default là `true`. `.env` hiện chỉ có `REPORT_OUTPUT_DIR=reports`, chưa có `REPORT_WRITE_HTML`, nên runtime dùng default `true`.

Nguyên nhân trực tiếp trong source là `ReportService.analyse_one_report()` khởi tạo:

```python
html_report = HtmlReport()
if payload.options.render_html:
    ...
```

Vì vậy response `available=false`, `output_path=null`, `template_name=null` chỉ xảy ra khi nhánh `if payload.options.render_html` không chạy, tức request runtime đang thiếu hoặc đang gửi `"renderHtml": false`, hoặc process/service đang chạy chưa nhận đúng body/code mới. Trước khi sửa, code cũng skip HTML im lặng, không thêm warning/data source để nói rõ HTML bị bỏ qua vì request option.

Ngoài ra, nhánh `REPORT_WRITE_HTML=false` trước đó chưa đúng yêu cầu mới: có thể tạo `HtmlReport.available=true` dù không có `output_path`. Đã sửa để khi không ghi được file thì `available=false` và có warning rõ.

## 3. Source code đã kiểm tra

Đã kiểm tra các file chính:

- `analyse/.env.example`
- `analyse/src/analyse/config/settings.py`
- `analyse/src/analyse/api/routes.py`
- `analyse/src/analyse/api/dependencies.py`
- `analyse/src/analyse/schemas/report.py`
- `analyse/src/analyse/schemas/stock.py`
- `analyse/src/analyse/services/report_service.py`
- `analyse/src/analyse/services/markdown_service.py`
- `analyse/src/analyse/services/html_service.py`
- `analyse/src/analyse/services/report_file_service.py`
- `analyse/tests/*`
- `analyse/README.md`

Không thấy lỗi alias Pydantic trong source code.

## 4. Files/classes/functions đã chỉnh

| File | Thay đổi | Lý do |
|---|---|---|
| `analyse/src/analyse/services/report_service.py` | Sửa flow xuất Markdown/HTML, build Markdown cho cả appendix HTML, build/write HTML trong nhánh `renderHtml=true`, thêm warning/data source khi HTML bị tắt bởi request/env hoặc build/write lỗi | Đảm bảo HTML file thật được tạo khi request/config cho phép; không skip im lặng |
| `analyse/src/analyse/services/html_service.py` | Mở rộng `HtmlService.build()` nhận `data_sources` và `provider`, hiển thị thêm trong data coverage | HTML dùng cùng dữ liệu report và có thêm ngữ cảnh nguồn/provider |
| `analyse/tests/test_report_schema.py` | Thêm test alias `"renderHtml": true` | Khóa mapping `renderHtml -> render_html` |
| `analyse/tests/test_report_file_service.py` | Thêm test path tương đối cho `write_html()` | Đảm bảo trả path dạng `reports/{report_id}.html` khi output dir là `reports` |
| `analyse/tests/test_report_renderers.py` | Bổ sung assert section HTML tối thiểu, symbol, disclaimer, escape unsafe text | Khóa yêu cầu HTML service |
| `analyse/tests/test_analyse_one_flow.py` | Thêm test full flow có `renderMarkdown=true`, `renderHtml=true`; thêm test `REPORT_WRITE_HTML=false`; thêm test `renderHtml=false` | Khóa đúng behavior enabled/disabled và warning |
| `analyse/README.md` | Thêm section “Xuất báo cáo Markdown và HTML” | Hướng dẫn request/env/kiểm tra file thủ công |

## 5. Luồng xuất Markdown/HTML sau khi sửa

Luồng hiện tại:

1. Nếu `renderMarkdown=true` hoặc `renderHtml=true`, service build `markdown_content`.
2. Nếu `renderMarkdown=true` và `REPORT_WRITE_MARKDOWN=true`, ghi `reports/{report_id}.md`.
3. Nếu `renderHtml=true` và `REPORT_WRITE_HTML=true`, gọi `HtmlService.build(...)`.
4. Ghi `reports/{report_id}.html`.
5. Response chỉ đặt:
   - `markdown_report.available=true` khi có `markdown_output_path`.
   - `html_report.available=true` khi có `html_output_path`.
6. `data_sources` có status filesystem cho cả Markdown và HTML.
7. Nếu HTML bị skip do `renderHtml=false` hoặc `REPORT_WRITE_HTML=false`, response có warning rõ.

## 6. Cấu hình `.env` cần thiết

```env
REPORT_OUTPUT_DIR=reports
REPORT_WRITE_MARKDOWN=true
REPORT_WRITE_HTML=true
REPORT_INCLUDE_MARKDOWN_CONTENT_IN_RESPONSE=true
REPORT_INCLUDE_HTML_CONTENT_IN_RESPONSE=false
```

Nếu `REPORT_WRITE_HTML=false`, HTML file không được ghi và response có warning:

```text
Không xuất HTML vì REPORT_WRITE_HTML=false.
```

## 7. Request Postman đúng để xuất cả `.md` và `.html`

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
    "renderHtml": true,
    "capitalVnd": 100000000,
    "riskPerTradePct": 1.0,
    "maxPositionPct": 12.0
  }
}
```

Nếu vẫn nhận `html_report.available=false` với body này, Cần kiểm tra thêm request thực tế do client gửi, server process đã restart/reload chưa, và response `warnings`.

## 8. Response JSON kỳ vọng

```json
"markdown_report": {
  "available": true,
  "output_path": "reports/FPT_HOSE_20260622_125159.md",
  "content": "# Báo cáo phân tích cổ phiếu FPT..."
},
"html_report": {
  "available": true,
  "output_path": "reports/FPT_HOSE_20260622_125159.html",
  "content": null,
  "template_name": "HtmlService.build"
}
```

`data_sources` kỳ vọng có:

```json
{
  "name": "Report Markdown file",
  "type": "filesystem",
  "status": "success",
  "detail": "reports/FPT_HOSE_20260622_125159.md"
}
```

```json
{
  "name": "Report HTML file",
  "type": "filesystem",
  "status": "success",
  "detail": "reports/FPT_HOSE_20260622_125159.html"
}
```

## 9. Cách kiểm tra file trên ổ đĩa

```powershell
cd D:\SWD\BE_AI_Stock_Trend_Prediction\analyse
ls reports
start reports\<report_id>.html
Get-Content reports\<report_id>.md -Encoding UTF8
```

Tên `<report_id>` lấy từ `data.report_id` hoặc từ `markdown_report.output_path`.

## 10. Test đã thêm/chỉnh sửa

Đã thêm/chỉnh:

- Test alias `renderHtml: true`.
- Test `HtmlService.build()` có `<!doctype html>`, symbol, disclaimer, các section tối thiểu và escape unsafe text.
- Test `ReportFileService.write_html()` tạo file và trả relative path khi output dir là `reports`.
- Test full report flow với `renderMarkdown=true`, `renderHtml=true`.
- Test `REPORT_WRITE_HTML=false` trả unavailable và warning rõ.
- Test `renderHtml=false` trả unavailable và warning rõ.

## 11. Kết quả chạy test

Đã chạy:

```powershell
cd analyse
python -m pytest
```

Kết quả:

```text
33 passed in 2.11s
```

## 12. Rủi ro còn lại

- Nếu client/frontend gửi thiếu `"renderHtml": true` hoặc gửi `"renderHtml": false`, HTML sẽ không xuất; hiện response đã có warning để nhận biết.
- Nếu service đang chạy chưa reload code mới, response có thể vẫn theo behavior cũ; Cần kiểm tra thêm bằng cách restart `python run.py` hoặc server đang dùng.
- Nếu `REPORT_WRITE_HTML=false`, HTML file cố ý không được tạo.
- Nếu `REPORT_OUTPUT_DIR` trỏ tới thư mục không có quyền ghi, response sẽ có warning build/write lỗi.

## 13. Kết luận

Đã sửa flow xuất HTML để khi request có `renderHtml=true` và `REPORT_WRITE_HTML=true`, service build HTML thật, ghi `reports/{report_id}.html`, trả `html_report.available=true`, `output_path` thật và `template_name="HtmlService.build"`. Các trường hợp HTML bị tắt hoặc lỗi ghi file không còn im lặng mà có warning và data source status rõ ràng.
