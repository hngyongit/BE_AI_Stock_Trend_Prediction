# Báo cáo sửa Ban lãnh đạo, Bối cảnh thị trường và CafeF tài chính

## 1. Mục tiêu

Sửa contract dữ liệu trình bày trong `analyse` để backend trả sẵn dữ liệu user-facing: Ban lãnh đạo được làm giàu từ bảng cổ đông lớn khi tên cá nhân khớp, Bối cảnh VNINDEX/HoSE được chuẩn hóa từ nhiều alias dữ liệu thị trường, và CafeF tài chính vẫn được thử như nguồn đối chiếu khi bật cấu hình.

## 2. Source code đã đọc

Đã rà soát recursive thư mục `analyse`, bao gồm `.env`, `.env.example`, `README.md`, `run.py`, `pyproject.toml`, `requirements.txt`, `src/analyse/main.py`, `src/analyse/app.py`, các thư mục `api`, `config`, `clients`, `services`, `research`, `schemas`, `utils`, `tests` và `reports/debug`.

Các file trọng tâm đã đọc kỹ: `stock_data_service.py`, `summary_service.py`, `report_service.py`, `presentation_contract.py`, `html_service.py`, `markdown_service.py`, `cafef_company_adapter.py`, `cafef_financial_adapter.py`, `vietstock_financial_adapter.py`, `vietstock_peer_adapter.py` và các test liên quan.

## 3. Vấn đề ban đầu

`Ban lãnh đạo` có tên/chức vụ nhưng thiếu `Số cổ phiếu` và `Tỷ lệ sở hữu`, dù bảng `Cổ đông lớn` có dòng cá nhân tương ứng. Market context có dữ liệu nhưng UI vẫn nhận nhiều card `Chưa xác minh` do backend chỉ đọc một số key cũ. CafeF tài chính bị ghi `skipped` khi Vietstock BCTC thành công, trái yêu cầu dùng CafeF làm nguồn đối chiếu nếu được bật.

## 4. Nguyên nhân Ban lãnh đạo không có cổ phiếu/tỷ lệ sở hữu

CafeF company adapter trả `leadership` và `ownership` thành hai list riêng. Presentation chỉ truyền nguyên list `leadership`, không merge sang `ownership`, nên các dòng lãnh đạo không tự nhận được số cổ phiếu/tỷ lệ sở hữu dù bảng cổ đông có cùng cá nhân.

## 5. Cách merge Ban lãnh đạo với Cổ đông lớn

Thêm `StockDataService.enrich_leadership_with_ownership()`. Hàm duyệt từng dòng lãnh đạo, tìm cổ đông cá nhân khớp tên, rồi bổ sung `shares`, `ownership_percent`, `ownership_source`, `ownership_match`, `ownership_match_confidence` và `ownership_note`. Nếu không khớp, giữ `shares=null`, `ownership_percent=null`, `ownership_match="not_found"`.

## 6. Cách chuẩn hóa tên cá nhân

Thêm `normalize_vietnamese_person_name()` và `normalize_vietnamese_person_name_ascii()`. Logic trim/lowercase, bỏ kính ngữ `Ông`, `Bà`, `Mr.`, `Mrs.`, `Ms.`, chuẩn hóa khoảng trắng và tạo biến thể không dấu. Matching ưu tiên exact normalized name, sau đó accent-insensitive name, sau đó token-set an toàn. Các cổ đông tổ chức/quỹ/ngân hàng bị loại khỏi matching.

## 7. Nguyên nhân Bối cảnh VNINDEX/HoSE bị Chưa xác minh

`SummaryService._market_context_view()` chỉ đọc các key như `vnindex`, `change_percent`, `total_volume`, `total_value`, `regime_score`. Payload thực tế có thể dùng camelCase hoặc tên khác như `indexValue`, `changePercent`, `matchedVolume`, `tradingValueBillion`, `marketScore`, nên backend không map được sang card trình bày.

## 8. Cách chuẩn hóa market context

Thêm normalizer trong `SummaryService` để map alias: `indexValue` -> `index_value`, `changePercent` -> `change_percent`, `matchedVolume`/`volume` -> `liquidity`, `tradingValueBillion` -> `trading_value_billion`, `marketScore`/`healthScore` -> `market_health_score`. `market_context_view` trả card user-ready và chỉ card thiếu dữ liệu mới hiển thị `Chưa xác minh`.

## 9. Nguyên nhân CafeF tài chính bị skipped

Trong `ReportService._apply_financial_fallback()`, sau khi Vietstock Finance trả `valid_periods`, code thêm source `CafeF BCTC` với `status="skipped"` và `return` sớm. Vì vậy CafeF không được thử dù `ENABLE_CAFEF_FINANCIAL_FALLBACK=true`.

## 10. Cách sửa để vẫn đọc CafeF tài chính

Đổi flow tài chính: Vietstock vẫn là nguồn BCTC chính khi dữ liệu nội bộ thiếu, nhưng không return sớm sau khi Vietstock thành công. Nếu CafeF financial fallback bật, service vẫn gọi `cafef_financial_adapter.fetch()` để đối chiếu/bổ sung. Nếu CafeF có kỳ hợp lệ, dữ liệu được merge bằng cơ chế fallback hiện có; nếu nguồn chính đã đầy đủ, CafeF được giữ như `_financial_fallback`.

## 11. Cách xử lý CafeF timeout/periods=0

Nếu CafeF timeout, source user-facing là `failed` với nhãn `Chưa lấy được`. Nếu CafeF tải được nhưng không có kỳ hợp lệ, source là `insufficient` với nhãn `Chưa đủ dữ liệu`. Không hiển thị URL, `periods=0`, timeout ms hay `page.goto` trong `data_sources`.

## 12. Cách sửa Nguồn đã sử dụng

`presentation_contract.py` tiếp tục sanitize tên nguồn thành `CafeF tài chính`, `Vietstock Finance BCTC`, `CafeF thông tin doanh nghiệp`, `Vietstock peer cùng ngành`. Riêng `skipped` cho CafeF tài chính không còn diễn giải là “Vietstock đã đủ”, mà chỉ dùng cho cấu hình/chính sách không gọi nguồn.

## 13. Debug artifacts đã thêm

Khi bật debug extraction, service ghi:

- `reports/debug/{symbol}_leadership_ownership_merge.json`
- `reports/debug/{symbol}_market_context_normalized.json`
- `reports/debug/{symbol}_cafef_financial_attempt.json`

Các file này chứa thông tin kỹ thuật cần thiết cho developer, không được đưa vào source rows user-facing và không chứa token/API key.

## 14. Files/classes/functions đã chỉnh

| File | Thay đổi | Lý do |
| ---- | -------- | ----- |
| `analyse/src/analyse/services/stock_data_service.py` | Thêm normalize tên cá nhân, loại tổ chức, merge leadership/ownership, debug merge payload | Làm giàu Ban lãnh đạo bằng cổ đông lớn khi match an toàn |
| `analyse/src/analyse/services/summary_service.py` | Thêm market context normalizer, card formatter, health label và market debug payload | Map alias VNINDEX/HoSE và tránh `Chưa xác minh` toàn section |
| `analyse/src/analyse/services/report_service.py` | Bỏ return sớm/skipped CafeF sau Vietstock, luôn attempt CafeF khi bật, thêm debug artifacts | CafeF tài chính là nguồn đối chiếu/bổ sung không blocking |
| `analyse/src/analyse/services/presentation_contract.py` | Sửa summary/detail user-facing cho CafeF financial failed/insufficient/skipped | Không hiển thị thuật ngữ kỹ thuật hoặc lý do skipped sai |
| `analyse/src/analyse/services/html_service.py` | Cột ghi chú Ban lãnh đạo ưu tiên `ownership_note`/`ownership_source` | HTML report thấy nguồn đối chiếu cổ đông lớn |
| `analyse/src/analyse/services/markdown_service.py` | Cột ghi chú Ban lãnh đạo ưu tiên `ownership_note`/`ownership_source` | Markdown report nhất quán với JSON/HTML |
| `analyse/tests/test_summary_scoring.py` | Thêm tests normalize tên, merge leadership, market alias/card | Bảo vệ data contract presentation |
| `analyse/tests/test_analyse_one_flow.py` | Sửa test CafeF không còn skipped; thêm debug attempt test | Bảo vệ flow CafeF financial mới |
| `analyse/tests/test_presentation_contract.py` | Cập nhật wording skipped và detail CafeF financial | Bảo vệ source list user-facing |
| `analyse/README.md` | Bổ sung tài liệu merge lãnh đạo, market normalizer, CafeF attempt và debug artifacts | Hướng dẫn developer vận hành/debug |

## 15. Test đã thêm/chạy

Đã thêm/cập nhật tests cho: `Ông/Bà` name normalization, leadership/shareholder merge, không match tổ chức, market alias mapping, per-card missing market field, CafeF vẫn được attempt khi Vietstock thành công, CafeF timeout/zero-period source status, debug artifact và source sanitization.

## 16. Kết quả test

Đã chạy trong thư mục `analyse`:

```bash
python -m pytest -q
```

Kết quả: `159 passed`. Có warning deprecation sẵn của FastAPI `on_event`, không phải lỗi test.

## 17. Cách test bằng Postman

Gửi `POST /api/ai-reports/analyse-one` với header `Authorization: Bearer <token đăng nhập>` và body có `symbol`, `scopeExchange`, `options.renderMarkdown=false`, `options.renderHtml=false`. Kiểm tra response vẫn có `{ code, message, data }`, `data.data_sources`, `data.summary.report_presentation.business_overview`, `data.summary.report_presentation.market_context_view`.

## 18. Cách kiểm tra trên frontend

Mở report của mã có dữ liệu CafeF ban lãnh đạo/cổ đông lớn. Bảng Ban lãnh đạo phải hiển thị số cổ phiếu/tỷ lệ sở hữu khi tên cá nhân match. Bối cảnh VNINDEX/HoSE phải điền các card có dữ liệu tương ứng. `Nguồn đã sử dụng` phải có `CafeF tài chính` ở trạng thái `Đã ghi nhận`, `Ghi nhận một phần`, `Chưa đủ dữ liệu` hoặc `Chưa lấy được`, không bị `skipped` chỉ vì Vietstock thành công.

## 19. Lưu ý nếu CafeF/Vietstock chặn hoặc thiếu dữ liệu

Không fabricate dữ liệu. Nếu CafeF không trả kỳ tài chính hợp lệ, report vẫn dùng nguồn BCTC đã chuẩn hóa khác nếu có. Nếu cổ đông lớn không có cá nhân khớp tên lãnh đạo hoặc chỉ có tổ chức/quỹ, leadership vẫn để `Chưa xác minh`. Nếu market payload không có index value nhưng có change/score, chỉ card chỉ số bị thiếu.

## 20. Kết luận

Backend hiện trả dữ liệu trình bày sạch hơn và giàu ngữ nghĩa tài chính hơn: leadership được đối chiếu với cổ đông lớn khi an toàn, market context đọc được nhiều biến thể field, CafeF tài chính không bị bỏ qua sai lý do, và debug detail vẫn nằm trong artifacts/logs thay vì user-facing report.
