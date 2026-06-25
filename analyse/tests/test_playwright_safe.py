import asyncio
import gc
import json

from analyse.config.settings import Settings
from analyse.research.cafef_financial_adapter import CAFEF_FINANCIAL_TIMEOUT_WARNING
from analyse.research.cafef_financial_adapter import PlaywrightCafeFFinancialRenderer
from analyse.schemas.report import DataSourceStatus
from analyse.services.report_service import ReportService
from analyse.utils.playwright_safe import PlaywrightTimeoutError
from analyse.utils.playwright_safe import TargetClosedError
from analyse.utils.playwright_safe import cancel_pending_tasks_safely
from analyse.utils.playwright_safe import close_playwright_objects_safely
from analyse.utils.playwright_safe import cleanup_playwright_runtime_safely
from analyse.utils.playwright_safe import gather_safely
from analyse.utils.playwright_safe import save_playwright_error_debug


def _target_closed() -> TargetClosedError:
    return TargetClosedError("Target page, context or browser has been closed")


def _playwright_timeout() -> PlaywrightTimeoutError:
    return PlaywrightTimeoutError("Timeout 60000ms exceeded")


async def _raise_target_closed():
    raise _target_closed()


async def _raise_timeout():
    raise _playwright_timeout()


def test_gather_safely_retrieves_playwright_task_exceptions():
    async def run():
        tasks = [asyncio.create_task(_raise_target_closed()), asyncio.create_task(_raise_timeout())]
        results = await gather_safely(tasks, label="test-playwright")
        assert any(isinstance(result, TargetClosedError) for result in results)
        assert any(isinstance(result, PlaywrightTimeoutError) for result in results)
        assert all(task.done() for task in tasks)

    asyncio.run(run())


def test_cancel_pending_tasks_safely_cancels_leftover_work():
    cleanup_completed = False

    async def sleeper():
        nonlocal cleanup_completed
        try:
            await asyncio.sleep(30)
        finally:
            cleanup_completed = True

    async def run():
        task = asyncio.create_task(sleeper())
        await asyncio.sleep(0)
        await cancel_pending_tasks_safely([task], label="test-cancel")
        assert task.done()
        assert task.cancelled()
        assert cleanup_completed

    asyncio.run(run())


def test_cancel_pending_tasks_safely_drains_already_failed_tasks():
    async def run():
        loop = asyncio.get_running_loop()
        contexts = []
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: contexts.append(context))
        try:
            tasks = [asyncio.create_task(_raise_target_closed())]
            await asyncio.sleep(0)
            assert tasks[0].done()

            await cancel_pending_tasks_safely(tasks, label="test-drain-done")

            del tasks
            gc.collect()
            await asyncio.sleep(0)
            assert contexts == []
        finally:
            loop.set_exception_handler(previous_handler)

    asyncio.run(run())


def test_close_playwright_objects_safely_ignores_close_errors():
    class CloseRaises:
        def __init__(self, exc):
            self.exc = exc

        async def close(self):
            raise self.exc

    async def run():
        await close_playwright_objects_safely(
            page=CloseRaises(_target_closed()),
            context=CloseRaises(_playwright_timeout()),
            browser=CloseRaises(RuntimeError("close failed")),
            label="test-close",
        )

    asyncio.run(run())


def test_cleanup_playwright_runtime_safely_drains_closes_and_writes_debug(tmp_path):
    class FakePage:
        def __init__(self):
            self.removed = None
            self.closed = False

        def remove_listener(self, event, handler):
            self.removed = (event, handler)

        async def close(self):
            self.closed = True

    class CloseTracks:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    async def run():
        page = FakePage()
        context = CloseTracks()
        browser = CloseTracks()
        handler = object()
        tasks = [asyncio.create_task(_raise_target_closed())]
        await asyncio.sleep(0)
        settings = Settings(
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        )

        await cleanup_playwright_runtime_safely(
            page=page,
            context=context,
            browser=browser,
            pending_tasks=tasks,
            response_handler=handler,
            label="test-runtime",
            debug_settings=settings,
            debug_source="CafeF thông tin doanh nghiệp",
            debug_url="https://cafef.vn/du-lieu/hose/vcb-ban-lanh-dao-so-huu.chn",
            debug_slug="cafef_company",
            debug_error=_target_closed(),
            debug_phase="response_handler",
        )

        assert page.removed == ("response", handler)
        assert page.closed is True
        assert context.closed is True
        assert browser.closed is True

    asyncio.run(run())

    payload_path = tmp_path / "reports" / "debug" / "VCB_cafef_company_playwright_error.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["source"] == "CafeF thông tin doanh nghiệp"
    assert payload["cleanup_completed"] is True


def test_playwright_error_debug_artifact_is_sanitized(tmp_path):
    settings = Settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        BACKEND_API_TOKEN="request-token",
        OPENAI_API_KEY="sk-secret",
    )

    save_playwright_error_debug(
        settings,
        source="Vietstock peer",
        url="https://finance.vietstock.vn/VCB/so-sanh-gia-co-phieu-cung-nganh.htm",
        slug="vietstock_peer",
        error=_target_closed(),
        phase="response_handler",
        pending_tasks_count=0,
        cleanup_completed=True,
    )

    payload_path = tmp_path / "reports" / "debug" / "VCB_vietstock_peer_playwright_error.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["source"] == "Vietstock peer"
    assert payload["used_playwright"] is True
    assert payload["error_type"] == "TargetClosedError"
    assert payload["cleanup_completed"] is True
    assert "request-token" not in serialized
    assert "sk-secret" not in serialized


def test_playwright_error_debug_artifact_scrubs_url_and_error_message(tmp_path):
    settings = Settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
    )

    save_playwright_error_debug(
        settings,
        source="CafeF tài chính",
        url="https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn?token=raw-token",
        slug="cafef_financial",
        error=RuntimeError("Authorization: Bearer raw-secret api_key=raw-key"),
        phase="page.goto",
        pending_tasks_count=0,
        cleanup_completed=True,
    )

    payload_path = tmp_path / "reports" / "debug" / "VCB_cafef_financial_playwright_error.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "raw-token" not in serialized
    assert "raw-secret" not in serialized
    assert "raw-key" not in serialized
    assert "<redacted>" in serialized


def test_cafef_financial_renderer_converts_target_closed_to_warning(monkeypatch, tmp_path):
    class FakeChromium:
        async def launch(self, **kwargs):
            raise _target_closed()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        async def __aenter__(self):
            return FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePlaywrightModule:
        @staticmethod
        def async_playwright():
            return FakePlaywrightContext()

    def fake_import(name):
        if name == "playwright.async_api":
            return FakePlaywrightModule
        raise AssertionError(name)

    monkeypatch.setattr("analyse.research.cafef_financial_adapter.importlib.import_module", fake_import)
    renderer = PlaywrightCafeFFinancialRenderer(
        Settings(
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        )
    )

    html, warnings = asyncio.run(renderer._fetch_rendered_html_direct("https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"))

    assert html is None
    assert any("TargetClosedError" in warning for warning in warnings)
    assert (tmp_path / "reports" / "debug" / "VCB_cafef_financial_playwright_error.json").exists()


def test_cafef_financial_renderer_converts_timeout_to_warning(monkeypatch, tmp_path):
    class FakeChromium:
        async def launch(self, **kwargs):
            raise _playwright_timeout()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        async def __aenter__(self):
            return FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePlaywrightModule:
        @staticmethod
        def async_playwright():
            return FakePlaywrightContext()

    def fake_import(name):
        if name == "playwright.async_api":
            return FakePlaywrightModule
        raise AssertionError(name)

    monkeypatch.setattr("analyse.research.cafef_financial_adapter.importlib.import_module", fake_import)
    renderer = PlaywrightCafeFFinancialRenderer(Settings(REPORT_OUTPUT_DIR=str(tmp_path / "reports")))

    html, warnings = asyncio.run(renderer._fetch_rendered_html_direct("https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"))

    assert html is None
    assert CAFEF_FINANCIAL_TIMEOUT_WARNING in warnings


def test_cafef_financial_renderer_uses_domcontentloaded_and_configured_timeout(monkeypatch, tmp_path):
    class FakePage:
        def __init__(self):
            self.goto_calls = []
            self.closed = False
            self.removed = None

        def on(self, event, handler):
            self.event = event
            self.handler = handler

        def remove_listener(self, event, handler):
            self.removed = (event, handler)

        async def goto(self, url, *, wait_until, timeout):
            self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})

        async def wait_for_selector(self, selector, *, timeout):
            return None

        async def wait_for_timeout(self, timeout):
            return None

        async def content(self):
            return "<html><table><tr><td>ok</td></tr></table></html>"

        async def close(self):
            self.closed = True

    fake_page = FakePage()

    class FakeContext:
        def __init__(self):
            self.closed = False

        async def new_page(self):
            return fake_page

        async def close(self):
            self.closed = True

    fake_context = FakeContext()

    class FakeBrowser:
        def __init__(self):
            self.closed = False

        async def new_context(self, **kwargs):
            return fake_context

        async def close(self):
            self.closed = True

    fake_browser = FakeBrowser()

    class FakeChromium:
        async def launch(self, **kwargs):
            return fake_browser

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        async def __aenter__(self):
            return FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePlaywrightModule:
        @staticmethod
        def async_playwright():
            return FakePlaywrightContext()

    def fake_import(name):
        if name == "playwright.async_api":
            return FakePlaywrightModule
        raise AssertionError(name)

    monkeypatch.setattr("analyse.research.cafef_financial_adapter.importlib.import_module", fake_import)
    renderer = PlaywrightCafeFFinancialRenderer(Settings(REPORT_OUTPUT_DIR=str(tmp_path / "reports"), CAFEF_FINANCIAL_TIMEOUT_MS=91000))

    html, warnings = asyncio.run(renderer._fetch_rendered_html_direct("https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"))

    assert warnings == []
    assert html is not None
    assert fake_page.goto_calls == [
        {
            "url": "https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn",
            "wait_until": "domcontentloaded",
            "timeout": 91000,
        }
    ]
    assert fake_page.removed == ("response", fake_page.handler)
    assert fake_page.closed is True
    assert fake_context.closed is True
    assert fake_browser.closed is True


def test_cafef_financial_timeout_writes_specific_debug_artifact(monkeypatch, tmp_path):
    class FakePage:
        def on(self, event, handler):
            self.event = event
            self.handler = handler

        def remove_listener(self, event, handler):
            self.removed = (event, handler)

        async def goto(self, url, *, wait_until, timeout):
            raise _playwright_timeout()

        async def close(self):
            return None

    class FakeContext:
        async def new_page(self):
            return FakePage()

        async def close(self):
            return None

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return FakeContext()

        async def close(self):
            return None

    class FakeChromium:
        async def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        async def __aenter__(self):
            return FakePlaywright()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePlaywrightModule:
        @staticmethod
        def async_playwright():
            return FakePlaywrightContext()

    def fake_import(name):
        if name == "playwright.async_api":
            return FakePlaywrightModule
        raise AssertionError(name)

    monkeypatch.setattr("analyse.research.cafef_financial_adapter.importlib.import_module", fake_import)
    settings = Settings(
        REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
        CAFEF_FINANCIAL_TIMEOUT_MS=90000,
        EXTERNAL_DATA_DEBUG_SAVE_EXTRACTION_JSON=True,
        BACKEND_API_TOKEN="request-token",
        OPENAI_API_KEY="sk-secret",
    )
    renderer = PlaywrightCafeFFinancialRenderer(settings)

    html, warnings = asyncio.run(renderer._fetch_rendered_html_direct("https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"))

    payload_path = tmp_path / "reports" / "debug" / "VCB_cafef_financial_timeout.json"
    generic_payload_path = tmp_path / "reports" / "debug" / "VCB_cafef_financial_playwright_error.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    generic_payload = json.loads(generic_payload_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    generic_serialized = json.dumps(generic_payload, ensure_ascii=False)
    assert html is None
    assert CAFEF_FINANCIAL_TIMEOUT_WARNING in warnings
    assert payload["source"] == "CafeF tài chính"
    assert payload["url"] == "https://cafef.vn/du-lieu/hose/vcb-tai-chinh.chn"
    assert payload["timeout_ms"] == 90000
    assert payload["wait_until"] == "domcontentloaded"
    assert payload["error_type"] == "PlaywrightTimeoutError"
    assert payload["phase"] == "page.goto"
    assert payload["fallback_used"] is True
    assert payload["report_blocked"] is False
    assert generic_payload["source"] == "CafeF tài chính"
    assert generic_payload["error_type"] == "PlaywrightTimeoutError"
    assert generic_payload["cleanup_completed"] is True
    assert "request-token" not in serialized
    assert "sk-secret" not in serialized
    assert "request-token" not in generic_serialized
    assert "sk-secret" not in generic_serialized


def test_failed_playwright_source_becomes_data_source_status(tmp_path):
    class FailedPeerAdapter:
        async def fetch(self, symbol: str):
            return {
                "source": "Vietstock Finance",
                "source_url": f"https://finance.vietstock.vn/{symbol}/so-sanh-gia-co-phieu-cung-nganh.htm",
                "status": "failed",
                "peers": [],
                "warnings": ["Vietstock peer rendering failed: TargetClosedError"],
                "technical_warnings": ["Target page, context or browser has been closed"],
            }

    service = ReportService(
        settings=Settings(
            REPORT_OUTPUT_DIR=str(tmp_path / "reports"),
            ENABLE_VIETSTOCK_PEER_FALLBACK=True,
        )
    )
    service.vietstock_peer_adapter = FailedPeerAdapter()
    data_sources: list[DataSourceStatus] = []

    _, warnings = asyncio.run(
        service._apply_peer_fallback(
            "VCB",
            "HOSE",
            {"symbol": "VCB", "industryPeerContext": {"peers": []}},
            data_sources,
            user_token="request-token",
        )
    )

    assert data_sources[-1].name == "Vietstock peer cùng ngành"
    assert data_sources[-1].status == "failed"
    assert any("TargetClosedError" in warning for warning in warnings)
