from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from analyse.utils.symbol_utils import normalize_symbol

try:  # Keep the analyse service importable even when browser deps are absent.
    from playwright.async_api import TargetClosedError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover - only used when Playwright is not installed

    class TargetClosedError(Exception):
        pass

    class PlaywrightTimeoutError(Exception):
        pass


logger = logging.getLogger(__name__)


def is_target_closed_error(exc: BaseException) -> bool:
    return isinstance(exc, TargetClosedError) or exc.__class__.__name__ == "TargetClosedError"


def is_playwright_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, PlaywrightTimeoutError):
        return True
    module = getattr(exc.__class__, "__module__", "")
    return exc.__class__.__name__ == "TimeoutError" and "playwright" in module.lower()


def safe_playwright_error_message(exc: BaseException, *, max_length: int = 180) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    if len(message) > max_length:
        message = message[: max_length - 3].rstrip() + "..."
    return message or "không có thông điệp chi tiết"


async def gather_safely(
    tasks: Iterable[asyncio.Task[Any]],
    *,
    label: str,
) -> list[Any]:
    safe_tasks = [task for task in tasks if task is not None]
    if not safe_tasks:
        return []

    results = await asyncio.gather(*safe_tasks, return_exceptions=True)
    for result in results:
        if not isinstance(result, BaseException):
            continue
        if isinstance(result, asyncio.CancelledError):
            logger.warning("[%s] Playwright task ended safely: CancelledError", label)
        elif is_target_closed_error(result) or is_playwright_timeout_error(result):
            logger.warning("[%s] Playwright task ended safely: %s", label, result.__class__.__name__)
        elif isinstance(result, Exception):
            logger.warning(
                "[%s] Playwright task failed safely: %s",
                label,
                result,
                exc_info=(type(result), result, result.__traceback__),
            )
        else:
            logger.warning("[%s] Playwright task ended safely: %s", label, result.__class__.__name__)
    return results


async def cancel_pending_tasks_safely(
    tasks: Iterable[asyncio.Task[Any]],
    *,
    label: str,
) -> None:
    safe_tasks = [task for task in tasks if task is not None and not task.done()]
    for task in safe_tasks:
        task.cancel()

    if safe_tasks:
        await asyncio.gather(*safe_tasks, return_exceptions=True)
        logger.info("[%s] Cancelled %s pending Playwright tasks", label, len(safe_tasks))


async def close_playwright_objects_safely(
    *,
    page: Any = None,
    context: Any = None,
    browser: Any = None,
    label: str,
) -> None:
    for name, obj in (("page", page), ("context", context), ("browser", browser)):
        if obj is None:
            continue
        close = getattr(obj, "close", None)
        if close is None:
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            if is_target_closed_error(exc):
                logger.debug("[%s] Playwright %s already closed", label, name)
            elif is_playwright_timeout_error(exc):
                logger.warning("[%s] Timeout while closing Playwright %s safely", label, name)
            else:
                logger.warning("[%s] Failed to close Playwright %s safely: %s", label, name, exc)


def remove_playwright_listener_safely(
    page: Any,
    event: str,
    handler: Any,
    *,
    label: str,
) -> None:
    if page is None:
        return
    try:
        remove_listener = getattr(page, "remove_listener", None)
        if remove_listener is not None:
            remove_listener(event, handler)
    except Exception as exc:
        if is_target_closed_error(exc):
            logger.debug("[%s] Playwright page already closed before removing %s listener", label, event)
        else:
            logger.warning("[%s] Failed to remove Playwright %s listener safely: %s", label, event, exc)


def infer_symbol_from_url(url: str) -> str:
    text = str(url or "")
    patterns = (
        r"finance\.vietstock\.vn/([A-Za-z0-9]{2,12})(?:/|$)",
        r"/du-lieu/[^/]+/([A-Za-z0-9]{2,12})-(?:ban-lanh-dao-so-huu|tai-chinh)\.chn",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_symbol(match.group(1)) or "UNKNOWN"
    return "UNKNOWN"


def save_playwright_error_debug(
    settings: Any,
    *,
    source: str,
    url: str,
    slug: str,
    error: BaseException,
    phase: str,
    pending_tasks_count: int,
    cleanup_completed: bool,
) -> None:
    if not _debug_enabled(settings):
        return

    symbol = infer_symbol_from_url(url)
    payload = {
        "source": source,
        "url": url,
        "used_playwright": True,
        "error_type": error.__class__.__name__,
        "error_message": safe_playwright_error_message(error, max_length=300),
        "phase": phase,
        "pending_tasks_count": pending_tasks_count,
        "cleanup_completed": cleanup_completed,
    }
    try:
        debug_dir = Path(getattr(settings, "report_output_dir", "reports")) / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{symbol}_{slug}_playwright_error.json" if slug else f"{symbol}_playwright_error.json"
        (debug_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - debug best effort only
        logger.warning("[playwright:%s] Could not save debug artifact: %s", slug or "error", exc)


def _debug_enabled(settings: Any) -> bool:
    return bool(
        getattr(settings, "external_data_debug_save_extraction_json", False)
        or getattr(settings, "vietstock_debug_save_extraction_json", False)
    )
