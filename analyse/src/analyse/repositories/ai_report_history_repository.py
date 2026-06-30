from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from analyse.config.settings import Settings, get_settings
from analyse.config.settings import ANALYSE_ROOT
from analyse.db.models import AiReportHistory
from analyse.db.session import HistoryStorageNotConfiguredError, get_db_session


class AiReportHistoryRepositoryError(RuntimeError):
    """Storage error hidden from API consumers."""


@dataclass(frozen=True)
class AiReportHistoryFilters:
    symbol: str | None = None
    exchange: str | None = None
    provider: str | None = None
    model: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None


class AiReportHistoryRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def create(self, values: dict[str, Any]) -> AiReportHistory:
        try:
            with get_db_session(self.settings) as session:
                row = AiReportHistory(**values)
                session.add(row)
                session.flush()
                session.refresh(row)
                return row
        except HistoryStorageNotConfiguredError:
            raise
        except SQLAlchemyError as exc:
            raise AiReportHistoryRepositoryError("Không lưu được lịch sử báo cáo AI.") from exc
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không lưu được lịch sử báo cáo AI.") from exc

    def list_by_user(
        self,
        mongo_user_id: str,
        *,
        filters: AiReportHistoryFilters | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[AiReportHistory]:
        safe_page, safe_limit = self._safe_page_limit(page, limit)
        offset = (safe_page - 1) * safe_limit
        try:
            with get_db_session(self.settings) as session:
                stmt = self._apply_filters(select(AiReportHistory), mongo_user_id, filters)
                stmt = stmt.order_by(AiReportHistory.created_at.desc()).offset(offset).limit(safe_limit)
                return list(session.scalars(stmt).all())
        except HistoryStorageNotConfiguredError:
            raise
        except SQLAlchemyError as exc:
            raise AiReportHistoryRepositoryError("Không đọc được lịch sử báo cáo AI.") from exc
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được lịch sử báo cáo AI.") from exc

    def count_by_user(self, mongo_user_id: str, *, filters: AiReportHistoryFilters | None = None) -> int:
        try:
            with get_db_session(self.settings) as session:
                stmt = self._apply_filters(select(func.count()).select_from(AiReportHistory), mongo_user_id, filters)
                return int(session.scalar(stmt) or 0)
        except HistoryStorageNotConfiguredError:
            raise
        except SQLAlchemyError as exc:
            raise AiReportHistoryRepositoryError("Không đếm được lịch sử báo cáo AI.") from exc
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đếm được lịch sử báo cáo AI.") from exc

    def get_by_id_for_user(self, history_id: str, mongo_user_id: str) -> AiReportHistory | None:
        try:
            with get_db_session(self.settings) as session:
                stmt = select(AiReportHistory).where(AiReportHistory.id == history_id, AiReportHistory.mongo_user_id == mongo_user_id)
                return session.scalars(stmt).first()
        except HistoryStorageNotConfiguredError:
            raise
        except SQLAlchemyError as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc

    def get_by_report_id_for_user(self, report_id: str, mongo_user_id: str) -> AiReportHistory | None:
        try:
            with get_db_session(self.settings) as session:
                stmt = select(AiReportHistory).where(AiReportHistory.report_id == report_id, AiReportHistory.mongo_user_id == mongo_user_id)
                return session.scalars(stmt).first()
        except HistoryStorageNotConfiguredError:
            raise
        except SQLAlchemyError as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc

    def delete_by_id_for_user(self, history_id: str, mongo_user_id: str) -> bool:
        try:
            with get_db_session(self.settings) as session:
                stmt = delete(AiReportHistory).where(AiReportHistory.id == history_id, AiReportHistory.mongo_user_id == mongo_user_id)
                result = session.execute(stmt)
                return bool(result.rowcount)
        except HistoryStorageNotConfiguredError:
            raise
        except SQLAlchemyError as exc:
            raise AiReportHistoryRepositoryError("Không xóa được lịch sử báo cáo AI.") from exc
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không xóa được lịch sử báo cáo AI.") from exc

    def _apply_filters(
        self,
        stmt: Select[tuple[Any, ...]] | Select[tuple[AiReportHistory]],
        mongo_user_id: str,
        filters: AiReportHistoryFilters | None,
    ):
        stmt = stmt.where(AiReportHistory.mongo_user_id == mongo_user_id)
        if not filters:
            return stmt
        if filters.symbol:
            stmt = stmt.where(AiReportHistory.symbol == filters.symbol.upper())
        if filters.exchange:
            stmt = stmt.where(AiReportHistory.exchange == filters.exchange.upper())
        if filters.provider:
            stmt = stmt.where(AiReportHistory.provider == filters.provider)
        if filters.model:
            stmt = stmt.where(AiReportHistory.model == filters.model)
        if filters.from_date:
            stmt = stmt.where(AiReportHistory.created_at >= filters.from_date)
        if filters.to_date:
            stmt = stmt.where(AiReportHistory.created_at <= filters.to_date)
        return stmt

    def _safe_page_limit(self, page: int, limit: int) -> tuple[int, int]:
        safe_page = max(1, int(page or 1))
        safe_limit = min(100, max(1, int(limit or 20)))
        return safe_page, safe_limit


class FileAiReportHistoryRepository:
    """Local JSON repository used when SQL Server is not configured."""

    storage_name = "file"
    _lock = threading.RLock()

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_dir = self._resolve_dir(getattr(self.settings, "ai_report_history_dir", "storage/ai_reports"))
        self.index_path = self.base_dir / "index.json"

    def create(self, values: dict[str, Any]) -> Any:
        try:
            with self._lock:
                self.base_dir.mkdir(parents=True, exist_ok=True)
                report_id = self._text(values.get("report_id"), "unknown")
                history_id = self._text(values.get("id"), "") or str(uuid4())
                created_at = self._parse_datetime(self._report_generated_at(values.get("report_json"))) or datetime.now(timezone.utc)
                row = self._row_from_values(values, history_id=history_id, created_at=created_at)
                detail_payload = {"metadata": self._metadata_from_row(row), "report_json": self._json_object(values.get("report_json"))}
                self._atomic_write_json(self.base_dir / f"{self._safe_filename(report_id)}.json", detail_payload)

                index = self._read_index()
                items = [item for item in index.get("items", []) if item.get("report_id") != report_id and item.get("id") != history_id]
                items.append(self._metadata_from_row(row))
                index["items"] = self._sort_items(items)
                self._atomic_write_json(self.index_path, index)
                return row
        except AiReportHistoryRepositoryError:
            raise
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không lưu được lịch sử báo cáo AI.") from exc

    def list_by_user(
        self,
        mongo_user_id: str,
        *,
        filters: AiReportHistoryFilters | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[Any]:
        safe_page, safe_limit = self._safe_page_limit(page, limit)
        offset = (safe_page - 1) * safe_limit
        try:
            items = self._filtered_items(mongo_user_id, filters)
            return [self._row_from_metadata(item) for item in items[offset : offset + safe_limit]]
        except AiReportHistoryRepositoryError:
            raise
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được lịch sử báo cáo AI.") from exc

    def count_by_user(self, mongo_user_id: str, *, filters: AiReportHistoryFilters | None = None) -> int:
        try:
            return len(self._filtered_items(mongo_user_id, filters))
        except AiReportHistoryRepositoryError:
            raise
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đếm được lịch sử báo cáo AI.") from exc

    def get_by_id_for_user(self, history_id: str, mongo_user_id: str) -> Any | None:
        try:
            target = str(history_id or "").strip()
            for item in self._filtered_items(mongo_user_id, None):
                if str(item.get("id") or "") == target:
                    return self._detail_row(item)
            return None
        except AiReportHistoryRepositoryError:
            raise
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc

    def get_by_report_id_for_user(self, report_id: str, mongo_user_id: str) -> Any | None:
        try:
            target = str(report_id or "").strip()
            for item in self._filtered_items(mongo_user_id, None):
                if str(item.get("report_id") or "") == target:
                    return self._detail_row(item)
            return None
        except AiReportHistoryRepositoryError:
            raise
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc

    def delete_by_id_for_user(self, history_id: str, mongo_user_id: str) -> bool:
        try:
            with self._lock:
                index = self._read_index()
                items = list(index.get("items", []))
                kept = []
                deleted: dict[str, Any] | None = None
                for item in items:
                    if str(item.get("id") or "") == str(history_id) and str(item.get("mongo_user_id") or "") == str(mongo_user_id):
                        deleted = item
                        continue
                    kept.append(item)
                if deleted is None:
                    return False
                index["items"] = kept
                self._atomic_write_json(self.index_path, index)
                report_id = self._text(deleted.get("report_id"), "")
                if report_id:
                    try:
                        (self.base_dir / f"{self._safe_filename(report_id)}.json").unlink()
                    except FileNotFoundError:
                        pass
                return True
        except AiReportHistoryRepositoryError:
            raise
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không xóa được lịch sử báo cáo AI.") from exc

    def _filtered_items(self, mongo_user_id: str, filters: AiReportHistoryFilters | None) -> list[dict[str, Any]]:
        index = self._read_index()
        items = [item for item in index.get("items", []) if str(item.get("mongo_user_id") or "") == str(mongo_user_id)]
        if filters:
            if filters.symbol:
                items = [item for item in items if str(item.get("symbol") or "").upper() == filters.symbol.upper()]
            if filters.exchange:
                items = [item for item in items if str(item.get("exchange") or "").upper() == filters.exchange.upper()]
            if filters.provider:
                items = [item for item in items if str(item.get("provider") or "") == filters.provider]
            if filters.model:
                items = [item for item in items if str(item.get("model") or "") == filters.model]
            if filters.from_date:
                items = [item for item in items if self._parse_datetime(item.get("created_at")) and self._parse_datetime(item.get("created_at")) >= self._aware(filters.from_date)]
            if filters.to_date:
                items = [item for item in items if self._parse_datetime(item.get("created_at")) and self._parse_datetime(item.get("created_at")) <= self._aware(filters.to_date)]
        return self._sort_items(items)

    def _detail_row(self, item: dict[str, Any]) -> Any:
        detail_path = self.base_dir / f"{self._safe_filename(item.get('report_id'))}.json"
        if not detail_path.exists():
            return self._row_from_metadata({**item, "report_json": "{}"})
        try:
            payload = json.loads(detail_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được chi tiết lịch sử báo cáo AI.") from exc
        report_json = payload.get("report_json") if isinstance(payload, dict) else {}
        return self._row_from_metadata({**item, "report_json": json.dumps(report_json if isinstance(report_json, dict) else {}, ensure_ascii=False)})

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"items": []}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AiReportHistoryRepositoryError("Không đọc được lịch sử báo cáo AI.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise AiReportHistoryRepositoryError("Không đọc được lịch sử báo cáo AI.")
        return payload

    def _row_from_values(self, values: dict[str, Any], *, history_id: str, created_at: datetime) -> Any:
        return SimpleNamespace(
            id=history_id,
            report_id=self._text(values.get("report_id"), "unknown"),
            mongo_user_id=self._text(values.get("mongo_user_id"), "unknown"),
            user_email=values.get("user_email"),
            mongo_watchlist_id=values.get("mongo_watchlist_id"),
            mongo_stock_id=values.get("mongo_stock_id"),
            symbol=self._text(values.get("symbol"), "UNKNOWN").upper(),
            exchange=self._text(values.get("exchange"), "HOSE").upper(),
            company=values.get("company"),
            provider=self._text(values.get("provider"), "unknown"),
            model=self._text(values.get("model"), "unknown"),
            risk_profile=values.get("risk_profile"),
            time_horizon=values.get("time_horizon"),
            include_external_research=bool(values.get("include_external_research", True)),
            total_score=values.get("total_score"),
            risk_score=values.get("risk_score"),
            data_confidence=values.get("data_confidence"),
            decision_label=values.get("decision_label"),
            report_json=values.get("report_json") or "{}",
            summary_snapshot=values.get("summary_snapshot"),
            source_hash=values.get("source_hash"),
            request_hash=values.get("request_hash"),
            created_at=created_at,
            updated_at=created_at,
        )

    def _row_from_metadata(self, item: dict[str, Any]) -> Any:
        created_at = self._parse_datetime(item.get("created_at")) or datetime.now(timezone.utc)
        return SimpleNamespace(
            id=self._text(item.get("id"), ""),
            report_id=self._text(item.get("report_id"), ""),
            mongo_user_id=self._text(item.get("mongo_user_id"), ""),
            user_email=item.get("user_email"),
            mongo_watchlist_id=item.get("mongo_watchlist_id"),
            mongo_stock_id=item.get("mongo_stock_id"),
            symbol=self._text(item.get("symbol"), "UNKNOWN"),
            exchange=self._text(item.get("exchange"), "HOSE"),
            company=item.get("company") or item.get("company_name"),
            provider=self._text(item.get("provider"), "unknown"),
            model=self._text(item.get("model"), "unknown"),
            risk_profile=item.get("risk_profile"),
            time_horizon=item.get("time_horizon"),
            include_external_research=bool(item.get("include_external_research", True)),
            total_score=item.get("total_score") if item.get("total_score") is not None else item.get("score"),
            risk_score=item.get("risk_score"),
            data_confidence=item.get("data_confidence"),
            decision_label=item.get("decision_label") or item.get("status"),
            report_json=item.get("report_json") or "{}",
            summary_snapshot=item.get("summary_snapshot"),
            source_hash=item.get("source_hash"),
            request_hash=item.get("request_hash"),
            created_at=created_at,
            updated_at=created_at,
        )

    def _metadata_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "report_id": row.report_id,
            "mongo_user_id": row.mongo_user_id,
            "user_email": row.user_email,
            "mongo_watchlist_id": row.mongo_watchlist_id,
            "mongo_stock_id": row.mongo_stock_id,
            "symbol": row.symbol,
            "exchange": row.exchange,
            "company": row.company,
            "company_name": row.company,
            "provider": row.provider,
            "model": row.model,
            "risk_profile": row.risk_profile,
            "time_horizon": row.time_horizon,
            "include_external_research": row.include_external_research,
            "total_score": row.total_score,
            "score": row.total_score,
            "risk_score": row.risk_score,
            "risk_level": row.decision_label,
            "data_confidence": row.data_confidence,
            "decision_label": row.decision_label,
            "status": row.decision_label,
            "created_at": self._iso(row.created_at),
            "generated_at": self._iso(row.created_at),
        }

    def _report_generated_at(self, report_json_text: Any) -> str | None:
        data = self._json_object(report_json_text).get("data", {})
        return data.get("generated_at") if isinstance(data, dict) else None

    def _json_object(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _sort_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: self._parse_datetime(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def _resolve_dir(self, value: str) -> Path:
        if str(value or "").strip() == "storage/ai_reports":
            report_output_dir = Path(str(getattr(self.settings, "report_output_dir", "reports") or "reports"))
            if str(report_output_dir) != "reports":
                base = report_output_dir if report_output_dir.is_absolute() else ANALYSE_ROOT / report_output_dir
                return base.parent / "ai_reports"
        path = Path(str(value or "storage/ai_reports"))
        return path if path.is_absolute() else ANALYSE_ROOT / path

    def _safe_filename(self, value: Any) -> str:
        text = self._text(value, "unknown")
        return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)[:160] or "unknown"

    def _safe_page_limit(self, page: int, limit: int) -> tuple[int, int]:
        safe_page = max(1, int(page or 1))
        safe_limit = min(100, max(1, int(limit or 20)))
        return safe_page, safe_limit

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return self._aware(value)
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return self._aware(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None

    def _aware(self, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    def _iso(self, value: datetime) -> str:
        return self._aware(value).isoformat()

    def _text(self, value: Any, fallback: str) -> str:
        clean = str(value or "").strip()
        return clean or fallback


def create_ai_report_history_repository(settings: Settings | None = None) -> Any:
    settings = settings or get_settings()
    storage = str(getattr(settings, "ai_report_history_storage", "auto") or "auto").strip().lower()
    has_sql_config = bool(str(getattr(settings, "ai_report_db_url", "") or "").strip())
    if storage in {"sql", "sqlserver", "mssql"}:
        return AiReportHistoryRepository(settings)
    if storage in {"file", "local", "json"}:
        return FileAiReportHistoryRepository(settings)
    if storage in {"disabled", "none", "off"}:
        return AiReportHistoryRepository(settings)
    if getattr(settings, "enable_ai_report_history", False) and has_sql_config:
        return AiReportHistoryRepository(settings)
    return FileAiReportHistoryRepository(settings)
