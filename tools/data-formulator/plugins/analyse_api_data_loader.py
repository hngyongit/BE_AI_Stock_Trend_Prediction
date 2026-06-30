"""Data Formulator plugin for analyse visualization.v1 datasets.

This plugin intentionally accepts only a dataset URL. It does not accept or
store bearer tokens. Use a signed URL with a short TTL for protected datasets,
or import JSON/CSV manually while signed URLs are not available.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pyarrow as pa

from data_formulator.data_loader.external_data_loader import ExternalDataLoader, MAX_IMPORT_ROWS


class AnalyseApiDataLoader(ExternalDataLoader):
    DISPLAY_NAME = "Analyse API"

    @staticmethod
    def list_params() -> list[dict[str, Any]]:
        return [
            {
                "name": "dataset_url",
                "type": "string",
                "required": True,
                "tier": "connection",
                "description": "URL returning an analyse visualization.v1 JSON response.",
            },
            {
                "name": "timeout_seconds",
                "type": "int",
                "required": False,
                "default": 20,
                "tier": "connection",
                "description": "HTTP timeout in seconds.",
            },
        ]

    @staticmethod
    def auth_instructions() -> str:
        return (
            "Provide a signed dataset URL or a local unauthenticated URL that returns "
            "the analyse `visualization.v1` JSON envelope. Do not paste user bearer "
            "tokens, OpenAI/Gemini keys, backend tokens, or database URLs here."
        )

    def __init__(self, params: dict[str, Any]):
        self.params = params or {}
        self.dataset_url = str(self.params.get("dataset_url") or "").strip()
        if not self.dataset_url:
            raise ValueError("dataset_url is required")
        self.timeout_seconds = int(self.params.get("timeout_seconds") or 20)
        self._dataset: dict[str, Any] | None = None

    def list_tables(self, table_filter: str | None = None) -> list[dict[str, Any]]:
        dataset = self._load_dataset()
        tables = dataset.get("tables") if isinstance(dataset.get("tables"), list) else []
        result = []
        filter_text = str(table_filter or "").strip().lower()
        for table in tables:
            if not isinstance(table, dict):
                continue
            name = str(table.get("name") or "").strip()
            if not name or (filter_text and filter_text not in name.lower()):
                continue
            columns = [
                {"name": str(column.get("name")), "type": str(column.get("type") or "string")}
                for column in table.get("columns", [])
                if isinstance(column, dict) and column.get("name")
            ]
            rows = table.get("rows") if isinstance(table.get("rows"), list) else []
            result.append(
                {
                    "name": name,
                    "metadata": {
                        "columns": columns,
                        "row_count": len(rows),
                        "description": table.get("description") or table.get("title"),
                    },
                }
            )
        return result

    def fetch_data_as_arrow(self, source_table: str, import_options: dict[str, Any] | None = None) -> pa.Table:
        if not source_table:
            raise ValueError("source_table must be provided")
        opts = import_options or {}
        size = min(int(opts.get("size", MAX_IMPORT_ROWS)), MAX_IMPORT_ROWS)
        table = self._find_table(source_table)
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        rows = rows[:size]
        columns = [
            str(column.get("name"))
            for column in table.get("columns", [])
            if isinstance(column, dict) and column.get("name")
        ]
        if not columns:
            columns = self._union_row_keys(rows)
        data = {column: [] for column in columns}
        for row in rows:
            if not isinstance(row, dict):
                continue
            for column in columns:
                data[column].append(row.get(column))
        return pa.table(data)

    def _find_table(self, source_table: str) -> dict[str, Any]:
        dataset = self._load_dataset()
        for table in dataset.get("tables") or []:
            if isinstance(table, dict) and table.get("name") == source_table:
                return table
        raise ValueError(f"Unknown analyse visualization table: {source_table}")

    def _load_dataset(self) -> dict[str, Any]:
        if self._dataset is not None:
            return self._dataset
        request = Request(self.dataset_url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ValueError(f"Analyse dataset endpoint returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load analyse dataset: {exc.__class__.__name__}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("schema_version") != "visualization.v1":
            raise ValueError("URL did not return an analyse visualization.v1 dataset")
        if not isinstance(data.get("tables"), list):
            raise ValueError("Analyse visualization dataset is missing tables")
        self._dataset = data
        return data

    def _union_row_keys(self, rows: list[Any]) -> list[str]:
        keys: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in row:
                if key not in keys:
                    keys.append(key)
        return keys
