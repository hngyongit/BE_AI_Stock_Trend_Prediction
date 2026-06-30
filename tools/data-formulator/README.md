# Data Formulator sidecar cho analyse

Thư mục này chứa phần setup phía dự án để chạy Microsoft Data Formulator như công cụ sidecar/local, không vendor source và không thêm dependency vào `analyse`.

## Chạy nhanh

PowerShell:

```powershell
.\tools\data-formulator\start-data-formulator.ps1
```

Bash:

```bash
./tools/data-formulator/start-data-formulator.sh
```

Mặc định Data Formulator chạy tại `http://localhost:5567`, dùng `DATA_FORMULATOR_HOME=.data_formulator` ở project root và plugin dir `tools/data-formulator/plugins`.

## Bảo mật

- Không mount `analyse/.env` vào Data Formulator.
- Không đưa `OPENAI_API_KEY`, `GEMINI_API_KEY`, `BACKEND_API_TOKEN`, `AI_REPORT_DB_URL` hoặc bearer token user vào plugin.
- Plugin `analyse_api_data_loader.py` chỉ nhận `dataset_url`; nên dùng signed URL TTL ngắn khi triển khai chia sẻ dataset.
- Nếu chưa có signed URL, ưu tiên import JSON/CSV thủ công từ endpoint `analyse`.
