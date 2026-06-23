from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import sys
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def ensure_windows_proactor_event_loop_policy() -> None:
    """Ensure Windows has subprocess-capable event loop policy for browser runtimes."""

    if sys.platform != "win32":
        return

    try:
        policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if policy_cls is None:
            logger.warning("WindowsProactorEventLoopPolicy is not available in this Python runtime.")
            return

        current_policy = asyncio.get_event_loop_policy()
        if not isinstance(current_policy, policy_cls):
            asyncio.set_event_loop_policy(policy_cls())
            logger.info("Set WindowsProactorEventLoopPolicy for Playwright subprocess support.")
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Could not set WindowsProactorEventLoopPolicy: %s", exc)


async def run_in_windows_proactor_thread(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine in a dedicated Proactor loop on Windows.

    Uvicorn/anyio may already have a running Selector loop on Windows, while
    Playwright needs subprocess support to launch Chromium. This helper keeps
    the public async API unchanged and isolates browser work in a fresh loop.
    """

    if sys.platform != "win32":
        return await coro_factory()

    parent_loop = asyncio.get_running_loop()

    def runner() -> T:
        ensure_windows_proactor_event_loop_policy()
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro_factory())
        finally:
            try:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    return await parent_loop.run_in_executor(None, runner)
