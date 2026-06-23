import asyncio

from analyse.utils import asyncio_windows


def test_windows_proactor_policy_helper_sets_policy_when_available(monkeypatch):
    original_policy = asyncio.get_event_loop_policy()

    class FakeProactorPolicy(asyncio.DefaultEventLoopPolicy):
        pass

    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    monkeypatch.setattr(asyncio_windows.asyncio, "WindowsProactorEventLoopPolicy", FakeProactorPolicy, raising=False)

    try:
        asyncio_windows.ensure_windows_proactor_event_loop_policy()
        assert isinstance(asyncio.get_event_loop_policy(), FakeProactorPolicy)
    finally:
        asyncio.set_event_loop_policy(original_policy)


def test_windows_proactor_thread_helper_returns_result(monkeypatch):
    original_policy = asyncio.get_event_loop_policy()

    class FakeProactorPolicy(asyncio.DefaultEventLoopPolicy):
        pass

    async def sample():
        return "ok"

    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    monkeypatch.setattr(asyncio_windows.asyncio, "WindowsProactorEventLoopPolicy", FakeProactorPolicy, raising=False)

    try:
        result = asyncio.run(asyncio_windows.run_in_windows_proactor_thread(lambda: sample()))
        assert result == "ok"
    finally:
        asyncio.set_event_loop_policy(original_policy)
