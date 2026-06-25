from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from analyse.config.settings import Settings, get_settings


class HistoryStorageNotConfiguredError(RuntimeError):
    """AI report history is disabled or missing SQL Server configuration."""


_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def _db_url(settings: Settings) -> str:
    url = str(settings.ai_report_db_url or "").strip()
    if not settings.enable_ai_report_history:
        raise HistoryStorageNotConfiguredError("Tính năng lịch sử báo cáo AI chưa được bật.")
    if not url:
        raise HistoryStorageNotConfiguredError("AI_REPORT_DB_URL chưa được cấu hình.")
    return url


def safe_db_url_for_log(db_url: str | None) -> str | None:
    if not str(db_url or "").strip():
        return None
    try:
        return str(make_url(str(db_url)).render_as_string(hide_password=True))
    except Exception:
        return "<invalid-db-url>"


def get_engine(settings: Settings | None = None) -> Engine:
    current_settings = settings or get_settings()
    url = _db_url(current_settings)
    engine = _ENGINE_CACHE.get(url)
    if engine is None:
        engine = create_engine(url, pool_pre_ping=True, future=True)
        _ENGINE_CACHE[url] = engine
    return engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    current_settings = settings or get_settings()
    url = _db_url(current_settings)
    factory = _SESSION_FACTORY_CACHE.get(url)
    if factory is None:
        factory = sessionmaker(bind=get_engine(current_settings), autoflush=False, autocommit=False, expire_on_commit=False, future=True)
        _SESSION_FACTORY_CACHE[url] = factory
    return factory


@contextmanager
def get_db_session(settings: Settings | None = None) -> Iterator[Session]:
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    for engine in _ENGINE_CACHE.values():
        engine.dispose()
    _ENGINE_CACHE.clear()
    _SESSION_FACTORY_CACHE.clear()
