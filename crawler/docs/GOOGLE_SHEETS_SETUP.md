# Google Sheets setup

1. Create a Google Cloud project.
2. Enable Google Sheets API and Google Drive API.
3. Create a service account.
4. Download the service account JSON credential.
5. Save it as `service_account.json` in the project root.
6. Open the JSON file locally and copy `client_email`.
7. Share the target Google Sheet with that email.
8. Create or let the crawler create the `CONFIG` sheet.

CONFIG columns:

```txt
symbol | slug | company_name_vi | profile_url | trading_stats_url
```

`slug` should identify the company profile page. Do not use trading-statistics or financial-tab URLs as profile slugs.
