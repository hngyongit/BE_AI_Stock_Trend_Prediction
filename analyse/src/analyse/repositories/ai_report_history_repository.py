from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from analyse.config.settings import Settings, get_settings
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
