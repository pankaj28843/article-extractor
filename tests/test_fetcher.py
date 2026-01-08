"""Unit tests for article_extractor.fetcher module.

Following Cosmic Python's principle: "Building a Fake Repository for Tests Is Now Trivial!"
We mock external dependencies (playwright, httpx) to test the fetcher logic in isolation.
"""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from article_extractor.types import NetworkOptions


def _install_dummy_playwright(monkeypatch):
    class DummyContext:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

        async def storage_state(self, *_, **__):  # pragma: no cover - helper API
            return None

        @property
        def pages(self):  # pragma: no cover - API parity
            return []

    class DummyBrowser:
        def __init__(self):
            self.context_options = None

        async def new_context(self, **kwargs):
            self.context_options = kwargs
            return DummyContext()

        async def close(self):
            return None

    class DummyPlaywright:
        def __init__(self):
            self.browser = DummyBrowser()
            self.chromium = SimpleNamespace(launch=self._launch)
            self.stopped = False

        async def _launch(self, **_kwargs):
            self.launch_kwargs = _kwargs
            return self.browser

        async def stop(self):
            self.stopped = True

    class DummyAsyncPlaywright:
        async def start(self):
            return DummyPlaywright()

    dummy_module = SimpleNamespace(async_playwright=lambda: DummyAsyncPlaywright())
    monkeypatch.setitem(sys.modules, "playwright.async_api", dummy_module)


def test_augment_context_merges_without_none():
    from article_extractor import fetcher as fetcher_module

    base = {"url": "https://example.com"}
    merged = fetcher_module._augment_context(base, status_code=None, attempts=2)

    assert merged["url"] == "https://example.com"
    assert merged["attempts"] == 2
    assert "status_code" not in merged


def test_augment_context_empty_returns_empty():
    from article_extractor import fetcher as fetcher_module

    assert (
        fetcher_module._augment_context(
            {},
        )
        == {}
    )


@pytest.mark.asyncio
async def test_fetcher_protocol_stubs():
    from article_extractor import fetcher as fetcher_module

    assert await fetcher_module.Fetcher.fetch(None, "https://example.com") is None
    assert await fetcher_module.Fetcher.__aenter__(None) is None
    assert await fetcher_module.Fetcher.__aexit__(None, None, None, None) is None


# Test PlaywrightFetcher internals


@pytest.mark.unit
class TestPlaywrightFetcherInit:
    """Test PlaywrightFetcher initialization."""

    def test_default_init(self):
        """PlaywrightFetcher should have sensible defaults."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        assert fetcher.headless is True
        assert fetcher.timeout == 30000
        assert fetcher._playwright is None
        assert fetcher._browser is None
        assert fetcher._context is None
        assert fetcher._semaphore is None

    def test_custom_init(self):
        """PlaywrightFetcher should accept custom headless and timeout."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher(headless=False, timeout=60000)
        assert fetcher.headless is False
        assert fetcher.timeout == 60000

    def test_max_concurrent_pages_constant(self):
        """MAX_CONCURRENT_PAGES should be 3."""
        from article_extractor import PlaywrightFetcher

        assert PlaywrightFetcher.MAX_CONCURRENT_PAGES == 3


@pytest.mark.unit
@pytest.mark.asyncio
class TestPlaywrightFetcherFetch:
    """Test PlaywrightFetcher.fetch() method."""

    async def test_fetch_without_context_raises(self):
        """Fetch without initializing context should raise RuntimeError."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()

        with pytest.raises(RuntimeError, match="not initialized"):
            await fetcher.fetch("https://example.com")

    async def test_fetch_success(self):
        """Fetch should return content and status code."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.return_value = SimpleNamespace(status=200)
        page.content = AsyncMock(side_effect=["<html>test</html>", "<html>test</html>"])

        with patch("asyncio.sleep", AsyncMock()):
            content, status = await fetcher.fetch("https://example.com")

        assert status == 200
        assert content == "<html>test</html>"
        page.close.assert_awaited_once()

    async def test_fetch_never_stabilizes_returns_latest(self):
        """Fetch should return latest content when stability checks never converge."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.return_value = SimpleNamespace(status=200)
        page.content = AsyncMock(side_effect=["<html>a</html>", "<html>b</html>"])

        with patch("asyncio.sleep", AsyncMock()):
            content, status = await fetcher.fetch(
                "https://example.com", max_stability_checks=2
            )

        assert status == 200
        assert content == "<html>b</html>"

    async def test_fetch_with_wait_for_selector(self):
        """Fetch should wait for selector if provided."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.return_value = SimpleNamespace(status=200)
        page.content = AsyncMock(
            side_effect=["<html>content</html>", "<html>content</html>"]
        )

        with patch("asyncio.sleep", AsyncMock()):
            _content, status = await fetcher.fetch(
                "https://example.com", wait_for_selector="#app"
            )

        page.wait_for_selector.assert_awaited_once_with("#app", timeout=5000)
        assert status == 200

    async def test_fetch_without_stability_check(self):
        """Fetch with wait_for_stability=False should return immediately."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.return_value = SimpleNamespace(status=200)
        page.content = AsyncMock(return_value="<html>immediate</html>")

        content, status = await fetcher.fetch(
            "https://example.com", wait_for_stability=False
        )

        assert status == 200
        assert content == "<html>immediate</html>"
        page.content.assert_awaited_once()

    async def test_fetch_selector_timeout_returns_408(self, caplog):
        """Selector timeout should return HTTP 408 with fallback content."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.return_value = SimpleNamespace(status=None)
        page.wait_for_selector.side_effect = asyncio.TimeoutError
        page.content = AsyncMock(return_value="<html>fallback</html>")

        caplog.set_level("WARNING")
        content, status = await fetcher.fetch(
            "https://example.com", wait_for_selector="#slow"
        )

        assert status == 408
        assert content == "<html>fallback</html>"
        assert any("Timed out" in message for message in caplog.messages)

    async def test_fetch_null_response_defaults_to_200(self):
        """Null response should default to status 200."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.return_value = None  # Null response
        page.content = AsyncMock(side_effect=["<html></html>", "<html></html>"])

        with patch("asyncio.sleep", AsyncMock()):
            _content, status = await fetcher.fetch(
                "https://example.com", wait_for_stability=True
            )

        assert status == 200


@pytest.mark.unit
@pytest.mark.asyncio
class TestPlaywrightFetcherStorageState:
    """Test storage state management."""

    async def test_clear_storage_state(self, tmp_path):
        """clear_storage_state should flush cookies, localStorage, and disk cache."""
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "state.json"
        storage_file.write_text("data", encoding="utf-8")
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)
        context = AsyncMock()
        page_one = AsyncMock()
        page_two = AsyncMock()
        context.pages = [page_one, page_two]
        fetcher._context = context

        await fetcher.clear_storage_state()

        context.clear_cookies.assert_awaited_once()
        assert page_one.evaluate.await_count == 1
        assert page_two.evaluate.await_count == 1
        assert not storage_file.exists()

    async def test_clear_cookies(self, tmp_path):
        """clear_cookies should clear cookies and delete storage file."""
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "cookies.json"
        storage_file.write_text("cookies", encoding="utf-8")
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)
        fetcher._context = AsyncMock()

        await fetcher.clear_cookies()

        fetcher._context.clear_cookies.assert_awaited_once()
        assert not storage_file.exists()

    async def test_clear_storage_state_without_context_deletes_file(self, tmp_path):
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "state.json"
        storage_file.write_text("data", encoding="utf-8")
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)

        await fetcher.clear_storage_state()

        assert not storage_file.exists()

    async def test_clear_cookies_without_context_deletes_file(self, tmp_path):
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "cookies.json"
        storage_file.write_text("data", encoding="utf-8")
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)

        await fetcher.clear_cookies()

        assert not storage_file.exists()

    async def test_clear_storage_state_without_file(self):
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        context = AsyncMock()
        context.pages = []
        fetcher._context = context

        await fetcher.clear_storage_state()

        context.clear_cookies.assert_awaited_once()

    async def test_clear_cookies_without_file(self):
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._context = AsyncMock()

        await fetcher.clear_cookies()

        fetcher._context.clear_cookies.assert_awaited_once()

    async def test_log_storage_state_missing_file(self, tmp_path):
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "missing.json"
        fetcher = PlaywrightFetcher(
            storage_state_file=storage_file, diagnostics_enabled=True
        )
        with patch.object(PlaywrightFetcher, "_log_diagnostic") as log_mock:
            fetcher._log_storage_state("start")

        extra = log_mock.call_args.kwargs["extra"]
        assert extra["storage_exists"] is False
        assert "storage_bytes" not in extra


@pytest.mark.unit
@pytest.mark.asyncio
class TestPlaywrightFetcherStorageQueue:
    async def test_storage_queue_uses_settings(self, tmp_path, monkeypatch):
        from article_extractor import PlaywrightFetcher
        from article_extractor.storage_queue import StorageQueue

        class _Settings:
            storage_queue_dir = tmp_path / "queue"
            storage_queue_max_entries = 5
            storage_queue_max_age_seconds = 12.0
            storage_queue_retention_seconds = 30.0

        monkeypatch.setattr(
            "article_extractor.settings.get_settings", lambda: _Settings
        )

        storage_file = tmp_path / "state.json"
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)

        assert isinstance(fetcher._storage_queue, StorageQueue)
        assert fetcher._storage_queue.queue_dir == _Settings.storage_queue_dir

    async def test_log_storage_state_handles_stat_error(self, tmp_path, monkeypatch):
        from pathlib import Path

        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "state.json"
        storage_file.write_text("data", encoding="utf-8")
        fetcher = PlaywrightFetcher(
            storage_state_file=storage_file, diagnostics_enabled=True
        )

        original_stat = Path.stat
        original_exists = Path.exists

        def _boom(self, *args, **kwargs):
            if self == storage_file:
                raise OSError("boom")
            return original_stat(self, *args, **kwargs)

        def _exists(self, *args, **kwargs):
            if self == storage_file:
                return True
            return original_exists(self, *args, **kwargs)

        monkeypatch.setattr(Path, "exists", _exists)
        monkeypatch.setattr(Path, "stat", _boom)

        fetcher._log_storage_state("load")

    async def test_persist_storage_payload_skips_when_unchanged(self, tmp_path):
        from article_extractor import PlaywrightFetcher
        from article_extractor.storage_queue import StorageSnapshot, compute_fingerprint

        storage_file = tmp_path / "state.json"
        payload = b"payload"
        fetcher = PlaywrightFetcher(
            storage_state_file=storage_file, diagnostics_enabled=True
        )
        fingerprint = compute_fingerprint(payload)
        fetcher._storage_snapshot = StorageSnapshot(
            path=storage_file, fingerprint=fingerprint, size=len(payload)
        )

        await fetcher._persist_storage_payload(payload)

        assert fetcher._storage_snapshot.fingerprint == fingerprint

    async def test_write_storage_direct_handles_disabled_storage(self):
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher(diagnostics_enabled=True)

        fetcher._write_storage_direct(b"payload")

    async def test_network_property_exposes_network(self):
        from article_extractor import PlaywrightFetcher

        network = NetworkOptions(user_agent="Agent")
        fetcher = PlaywrightFetcher(network=network)

        assert fetcher.network is network

    async def test_log_stability_summary_emits_when_enabled(self, caplog):
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher(diagnostics_enabled=True)
        caplog.set_level("INFO")

        fetcher._log_stability_summary(
            {"url": "https://example.com"},
            checks=2,
            stabilized=True,
            max_checks=5,
        )

        assert any(
            "Playwright stability summary" in record.message
            for record in caplog.records
        )

    async def test_aenter_handles_missing_storage_file(self, tmp_path, monkeypatch):
        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_check_playwright", lambda: True)
        _install_dummy_playwright(monkeypatch)

        storage_file = tmp_path / "missing.json"
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)

        entered = await fetcher.__aenter__()

        assert entered is fetcher
        assert "storage_state" not in fetcher._browser.context_options

        await fetcher.__aexit__(None, None, None)

    async def test_aexit_saves_storage_and_closes(self, tmp_path):
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "state.json"
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)
        context = AsyncMock()
        context.storage_state = AsyncMock(return_value={"cookies": []})
        fetcher._context = context
        browser = AsyncMock()
        playwright = AsyncMock()
        fetcher._browser = browser
        fetcher._playwright = playwright

        await fetcher.__aexit__(None, None, None)

        context.storage_state.assert_awaited_once()
        browser.close.assert_awaited_once()
        playwright.stop.assert_awaited_once()


class TestPlaywrightFetcherStorageEnv:
    def test_storage_state_alias_env_wins_over_legacy(self, tmp_path, monkeypatch):
        from article_extractor import PlaywrightFetcher

        alias_file = tmp_path / "alias.json"
        legacy_file = tmp_path / "legacy.json"
        monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(alias_file))
        monkeypatch.setenv("PLAYWRIGHT_STORAGE_STATE_FILE", str(legacy_file))

        fetcher = PlaywrightFetcher()

        assert fetcher.storage_state_file == alias_file

    def test_storage_state_falls_back_to_legacy_env(self, tmp_path, monkeypatch):
        from article_extractor import PlaywrightFetcher

        legacy_file = tmp_path / "legacy.json"
        monkeypatch.setenv("PLAYWRIGHT_STORAGE_STATE_FILE", str(legacy_file))

        fetcher = PlaywrightFetcher()

        assert fetcher.storage_state_file == legacy_file

    def test_runtime_env_override_without_module_reload(self, tmp_path, monkeypatch):
        from article_extractor import PlaywrightFetcher

        first_file = tmp_path / "first.json"
        monkeypatch.setenv("PLAYWRIGHT_STORAGE_STATE_FILE", str(first_file))

        fetcher_one = PlaywrightFetcher()
        assert fetcher_one.storage_state_file == first_file

        second_file = tmp_path / "second.json"
        monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(second_file))

        fetcher_two = PlaywrightFetcher()
        assert fetcher_two.storage_state_file == second_file


# Test HttpxFetcher


@pytest.mark.unit
class TestHttpxFetcherInit:
    """Test HttpxFetcher initialization."""

    def test_default_init(self):
        """HttpxFetcher should have sensible defaults."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        assert fetcher.timeout == 30.0
        assert fetcher.follow_redirects is True
        assert fetcher._client is None

    def test_custom_init(self):
        """HttpxFetcher should accept custom timeout and follow_redirects."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher(timeout=60.0, follow_redirects=False)
        assert fetcher.timeout == 60.0
        assert fetcher.follow_redirects is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestHttpxFetcherFetch:
    """Test HttpxFetcher.fetch() method."""

    async def test_fetch_without_client_raises(self):
        """Fetch without initializing client should raise RuntimeError."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()

        with pytest.raises(RuntimeError, match="not initialized"):
            await fetcher.fetch("https://example.com")

    async def test_fetch_success(self):
        """Fetch should return content and status code."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<html>test content</html>"
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response
        fetcher._client = mock_client

        content, status = await fetcher.fetch("https://example.com")

        assert status == 200
        assert content == "<html>test content</html>"
        mock_client.get.assert_awaited_once_with("https://example.com")

    async def test_fetch_respects_proxy_bypass(self):
        """HttpxFetcher should skip proxies for NO_PROXY hosts."""
        from article_extractor import HttpxFetcher

        network = NetworkOptions(
            proxy="http://proxy:8080", proxy_bypass=("example.com",)
        )
        fetcher = HttpxFetcher(network=network)
        mock_client = AsyncMock()
        mock_proxy_client = AsyncMock()
        mock_response = MagicMock(text="ok", status_code=200)
        mock_client.get.return_value = mock_response
        mock_proxy_client.get.return_value = mock_response
        fetcher._client = mock_client
        fetcher._proxy_client = mock_proxy_client

        await fetcher.fetch("https://example.com/article")
        await fetcher.fetch("https://other.com/article")

        mock_client.get.assert_any_await("https://example.com/article")
        mock_proxy_client.get.assert_awaited_once_with("https://other.com/article")

    async def test_fetch_retries_on_exception_with_diagnostics(self, caplog):
        """HttpxFetcher should retry transient errors and log diagnostics when enabled."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher(diagnostics_enabled=True)
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            RuntimeError("boom"),
            SimpleNamespace(text="<html>OK</html>", status_code=200),
        ]
        fetcher._client = mock_client

        caplog.set_level("INFO")
        content, status = await fetcher.fetch("https://example.com")

        assert status == 200
        assert "<html>OK</html>" in content
        assert mock_client.get.await_count == 2
        assert any(
            "httpx fetch exception" in record.message for record in caplog.records
        )

    async def test_fetch_retries_on_retryable_status_with_diagnostics(self, caplog):
        """Retryable HTTP status responses should trigger diagnostics and another attempt."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher(diagnostics_enabled=True)
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            SimpleNamespace(text="retry", status_code=502),
            SimpleNamespace(text="ok", status_code=200),
        ]
        fetcher._client = mock_client

        caplog.set_level("INFO")
        _, status = await fetcher.fetch("https://example.org")

        assert status == 200
        assert mock_client.get.await_count == 2
        assert any(
            "httpx retryable response" in record.message for record in caplog.records
        )

    async def test_fetch_retries_silently_when_diagnostics_disabled(self, caplog):
        """Retries still occur even when diagnostics logging stays off."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            SimpleNamespace(text="retry", status_code=502),
            SimpleNamespace(text="ok", status_code=200),
        ]
        fetcher._client = mock_client

        caplog.set_level("INFO")
        await fetcher.fetch("https://retry.example")

        assert mock_client.get.await_count == 2
        assert "httpx retryable response" not in caplog.text
        assert "httpx fetch summary" not in caplog.text


# Test get_default_fetcher


@pytest.mark.unit
class TestGetDefaultFetcher:
    """Test get_default_fetcher function."""

    def test_returns_playwright_when_available(self, monkeypatch):
        """Should return PlaywrightFetcher when playwright is available."""
        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        # Reset cache
        monkeypatch.setattr(fetcher_module, "_playwright_available", True)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        result = fetcher_module.get_default_fetcher(prefer_playwright=True)
        assert result is PlaywrightFetcher

    def test_returns_httpx_when_playwright_not_preferred(self, monkeypatch):
        """Should return HttpxFetcher when not preferring playwright."""
        from article_extractor import HttpxFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_playwright_available", True)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        result = fetcher_module.get_default_fetcher(prefer_playwright=False)
        assert result is HttpxFetcher

    def test_returns_httpx_when_playwright_unavailable(self, monkeypatch):
        """Should return HttpxFetcher when playwright not available."""
        from article_extractor import HttpxFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_playwright_available", False)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        result = fetcher_module.get_default_fetcher(prefer_playwright=True)
        assert result is HttpxFetcher

    def test_returns_playwright_when_only_available(self, monkeypatch):
        """Should return PlaywrightFetcher when only option."""
        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_playwright_available", True)
        monkeypatch.setattr(fetcher_module, "_httpx_available", False)

        result = fetcher_module.get_default_fetcher(prefer_playwright=False)
        assert result is PlaywrightFetcher

    def test_raises_when_no_fetcher_available(self, monkeypatch):
        """Should raise ImportError when no fetcher is available."""
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_playwright_available", False)
        monkeypatch.setattr(fetcher_module, "_httpx_available", False)

        with pytest.raises(ImportError, match="No fetcher available"):
            fetcher_module.get_default_fetcher()


# Test _check_playwright and _check_httpx


@pytest.mark.unit
class TestCheckFunctions:
    """Test availability check functions."""

    def test_check_playwright_returns_bool(self, monkeypatch):
        """_check_playwright should return a boolean."""
        from article_extractor import fetcher as fetcher_module

        # Reset cache
        monkeypatch.setattr(fetcher_module, "_playwright_available", None)

        result = fetcher_module._check_playwright()
        assert isinstance(result, bool)
        # Second call should return same cached value
        result2 = fetcher_module._check_playwright()
        assert result == result2

    def test_check_httpx_returns_bool(self, monkeypatch):
        """_check_httpx should return a boolean."""
        from article_extractor import fetcher as fetcher_module

        # Reset cache
        monkeypatch.setattr(fetcher_module, "_httpx_available", None)

        result = fetcher_module._check_httpx()
        assert isinstance(result, bool)
        # Second call should return same cached value
        result2 = fetcher_module._check_httpx()
        assert result == result2

    def test_check_playwright_handles_import_error(self, monkeypatch):
        import builtins

        from article_extractor import fetcher as fetcher_module

        real_import = builtins.__import__

        def _boom(name, *args, **kwargs):
            if name == "playwright.async_api":
                raise ImportError("no playwright")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(fetcher_module, "_playwright_available", None)
        monkeypatch.setattr(builtins, "__import__", _boom)

        assert fetcher_module._check_playwright() is False

    def test_check_httpx_handles_import_error(self, monkeypatch):
        import builtins

        from article_extractor import fetcher as fetcher_module

        real_import = builtins.__import__

        def _boom(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("no httpx")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(fetcher_module, "_httpx_available", None)
        monkeypatch.setattr(builtins, "__import__", _boom)

        assert fetcher_module._check_httpx() is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestPlaywrightFetcherContextManager:
    """Test PlaywrightFetcher context manager."""

    async def test_aenter_missing_playwright(self, monkeypatch):
        """__aenter__ without playwright should raise ImportError."""
        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_playwright_available", False)

        fetcher = PlaywrightFetcher()
        with pytest.raises(ImportError, match="playwright not installed"):
            async with fetcher:
                pass

    async def test_aenter_with_proxy(self, monkeypatch):
        """__aenter__ should use HTTP proxy from environment."""
        from article_extractor import PlaywrightFetcher

        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")

        fetcher = PlaywrightFetcher()

        try:
            async with fetcher:
                pass
        except ImportError:
            pytest.skip("Playwright not installed")

    async def test_aenter_initializes_browser_and_context(self, monkeypatch, tmp_path):
        """__aenter__ should launch browser, load storage, and create semaphore."""

        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_check_playwright", lambda: True)

        _install_dummy_playwright(monkeypatch)

        storage_file = tmp_path / "state.json"
        storage_file.write_text("{}", encoding="utf-8")
        network = NetworkOptions(
            proxy="http://proxy:8080", storage_state_path=storage_file
        )
        fetcher = PlaywrightFetcher(network=network, diagnostics_enabled=True)

        entered = await fetcher.__aenter__()

        assert entered is fetcher
        assert fetcher._browser is not None
        assert fetcher._context is not None
        assert fetcher._semaphore is not None
        assert fetcher._browser.context_options["storage_state"] == str(storage_file)

        await fetcher.__aexit__(None, None, None)

    async def test_aenter_skips_storage_when_disabled(self, monkeypatch):
        """__aenter__ should skip storage wiring when no path configured."""
        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_check_playwright", lambda: True)
        _install_dummy_playwright(monkeypatch)

        fetcher = PlaywrightFetcher(diagnostics_enabled=True)

        await fetcher.__aenter__()

        assert "storage_state" not in fetcher._browser.context_options
        assert fetcher._storage_lock is None

        await fetcher.__aexit__(None, None, None)

    async def test_aexit_saves_storage(self, tmp_path):
        """__aexit__ should save storage state."""
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "storage.json"

        fetcher = PlaywrightFetcher(storage_state_file=storage_file)
        mock_context = AsyncMock()
        mock_context.storage_state.return_value = {"cookies": ["session"]}
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        fetcher._context = mock_context
        fetcher._browser = mock_browser
        fetcher._playwright = mock_playwright

        await fetcher.__aexit__(None, None, None)

        assert mock_context.storage_state.await_count == 1
        assert mock_context.close.await_count == 1
        assert mock_browser.close.await_count == 1
        assert storage_file.exists()
        assert "session" in storage_file.read_text(encoding="utf-8")

    async def test_aexit_skips_storage_when_disabled(self):
        """__aexit__ should not attempt persistence when storage disabled."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        mock_context = AsyncMock()
        mock_context.storage_state = AsyncMock()
        mock_context.close = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        fetcher._context = mock_context
        fetcher._browser = mock_browser
        fetcher._playwright = mock_playwright

        await fetcher.__aexit__(None, None, None)

        mock_context.storage_state.assert_not_called()
        assert mock_context.close.await_count == 1
        assert mock_browser.close.await_count == 1
        assert mock_playwright.stop.await_count == 1

    async def test_aexit_without_context_or_browser(self):
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._context = None
        fetcher._browser = None
        fetcher._playwright = None

        await fetcher.__aexit__(None, None, None)

        assert fetcher._context is None
        assert fetcher._browser is None
        assert fetcher._playwright is None

    async def test_initialize_storage_queue_without_settings(
        self, monkeypatch, tmp_path
    ):
        from article_extractor import PlaywrightFetcher
        from article_extractor import settings as settings_module

        monkeypatch.setattr(settings_module, "get_settings", lambda: None)

        fetcher = PlaywrightFetcher(storage_state_file=tmp_path / "state.json")

        assert fetcher._storage_queue is not None

    async def test_persist_storage_payload_writes_via_queue(self, tmp_path):
        """_persist_storage_payload should leverage the storage queue."""
        from article_extractor import PlaywrightFetcher
        from article_extractor.storage_queue import normalize_payload

        storage_file = tmp_path / "state.json"
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)
        fetcher._storage_lock = asyncio.Lock()

        payload = normalize_payload({"cookies": ["queued"]})
        await fetcher._persist_storage_payload(payload)

        assert storage_file.exists()
        assert "queued" in storage_file.read_text(encoding="utf-8")

    async def test_persist_storage_payload_skips_when_disabled(self, caplog):
        """_persist_storage_payload should no-op when persistence disabled."""
        from article_extractor import PlaywrightFetcher
        from article_extractor.storage_queue import normalize_payload

        fetcher = PlaywrightFetcher(diagnostics_enabled=True)
        caplog.set_level("INFO")

        payload = normalize_payload({"cookies": ["noop"]})
        await fetcher._persist_storage_payload(payload)

        assert any(
            "Skipped Playwright storage persistence" in record.message
            for record in caplog.records
        )

    async def test_aexit_handles_storage_save_failure(self, tmp_path, caplog):
        """__aexit__ should handle storage save failure gracefully."""
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "readonly" / "storage.json"

        fetcher = PlaywrightFetcher(storage_state_file=storage_file)
        mock_context = AsyncMock()
        mock_context.storage_state.side_effect = RuntimeError("Cannot save")
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        fetcher._context = mock_context
        fetcher._browser = mock_browser
        fetcher._playwright = mock_playwright

        caplog.set_level("WARNING")
        await fetcher.__aexit__(None, None, None)

        assert any(
            "Failed to save storage state" in message for message in caplog.messages
        )


class TestPlaywrightDiagnostics:
    """Diagnostics helpers should expose storage metadata when enabled."""

    def test_storage_state_logging_includes_metadata(self, tmp_path, caplog):
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "storage.json"
        storage_file.write_text("{}", encoding="utf-8")
        fetcher = PlaywrightFetcher(
            diagnostics_enabled=True, storage_state_file=storage_file
        )

        caplog.set_level("INFO")
        fetcher._log_storage_state("load")

        matching = [
            record
            for record in caplog.records
            if record.message == "Playwright storage state"
        ]
        assert matching, "Expected diagnostic storage state log"
        record = matching[0]
        assert getattr(record, "storage_state", "") == str(storage_file)
        assert getattr(record, "storage_bytes", 0) == storage_file.stat().st_size

    def test_storage_state_logging_reports_disabled_when_unset(self, caplog):
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher(diagnostics_enabled=True)

        caplog.set_level("INFO")
        fetcher._log_storage_state("load")

        assert any(
            record.message == "Playwright storage disabled" for record in caplog.records
        )

    def test_storage_state_logging_disabled_by_default(self, tmp_path, caplog):
        from article_extractor import PlaywrightFetcher

        storage_file = tmp_path / "storage.json"
        storage_file.write_text("{}", encoding="utf-8")
        fetcher = PlaywrightFetcher(storage_state_file=storage_file)

        caplog.set_level("INFO")
        fetcher._log_storage_state("load")

        assert "Playwright storage state" not in caplog.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_playwright_wait_for_user_respects_timeout(monkeypatch):
    from article_extractor import PlaywrightFetcher

    fetcher = PlaywrightFetcher()
    fetcher.headless = False
    fetcher.user_interaction_timeout = 1.0

    sleep = AsyncMock()
    monkeypatch.setattr("article_extractor.fetcher.asyncio.sleep", sleep)

    await fetcher._maybe_wait_for_user(None)

    assert sleep.await_count >= 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestHttpxFetcherContextManager:
    """Test HttpxFetcher context manager."""

    async def test_aenter_missing_httpx(self, monkeypatch):
        """__aenter__ without httpx should raise ImportError."""
        from article_extractor import HttpxFetcher
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_httpx_available", False)

        fetcher = HttpxFetcher()
        with pytest.raises(ImportError, match="httpx not installed"):
            async with fetcher:
                pass

    async def test_aenter_creates_client(self):
        """__aenter__ should create httpx client."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher(timeout=60.0, follow_redirects=False)
        async with fetcher:
            assert fetcher._client is not None

    async def test_aenter_builds_proxy_client_with_isolated_headers(self, monkeypatch):
        """__aenter__ should build dedicated proxy client with copied headers."""
        from article_extractor import HttpxFetcher
        from article_extractor import fetcher as fetcher_module

        created_clients = []

        class DummyClient:
            def __init__(self, **kwargs):
                created_clients.append(self)
                self.kwargs = kwargs
                self.closed = 0

            async def aclose(self):
                self.closed += 1

        dummy_httpx = SimpleNamespace(AsyncClient=DummyClient)
        monkeypatch.setitem(sys.modules, "httpx", dummy_httpx)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        network = NetworkOptions(proxy="http://proxy:9000")
        fetcher = HttpxFetcher(network=network)

        async with fetcher:
            assert len(created_clients) == 2
            base_client, proxy_client = created_clients
            assert "proxies" not in base_client.kwargs
            assert proxy_client.kwargs["proxies"] == "http://proxy:9000"
            assert base_client.kwargs["headers"] == proxy_client.kwargs["headers"]
            assert base_client.kwargs["headers"] is not proxy_client.kwargs["headers"]

        assert created_clients[0].closed == 1
        assert created_clients[1].closed == 1

    async def test_aexit_closes_client(self):
        """__aexit__ should close httpx client."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        async with fetcher:
            pass

        assert fetcher._client is None

    async def test_aexit_closes_proxy_client(self):
        """__aexit__ should close both primary and proxy clients."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        base_client = SimpleNamespace(aclose=AsyncMock())
        proxy_client = SimpleNamespace(aclose=AsyncMock())
        fetcher._client = base_client
        fetcher._proxy_client = proxy_client

        await fetcher.__aexit__(None, None, None)

        base_client.aclose.assert_awaited_once()
        proxy_client.aclose.assert_awaited_once()
        assert fetcher._client is None
        assert fetcher._proxy_client is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestPlaywrightFetcherEdgeCases:
    """Test PlaywrightFetcher edge cases."""

    async def test_fetch_exception_closes_page(self):
        """Fetch should close page even if exception occurs."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._semaphore = asyncio.Semaphore(1)
        context = AsyncMock()
        fetcher._context = context

        page = AsyncMock()
        context.new_page.return_value = page
        page.goto.side_effect = RuntimeError("Navigation failed")

        with pytest.raises(RuntimeError):
            await fetcher.fetch("https://example.com")

        page.close.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
class TestHttpxFetcherEdgeCases:
    """Test HttpxFetcher edge cases."""

    async def test_fetch_httpx_exception(self):
        """Fetch should propagate httpx exceptions."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        mock_client = AsyncMock()
        mock_client.get.side_effect = RuntimeError("Network error")
        fetcher._client = mock_client

        with pytest.raises(RuntimeError, match="Network error"):
            await fetcher.fetch("https://example.com")


@pytest.mark.unit
class TestUserAgentSelection:
    def test_select_user_agent_prefers_explicit_override(self):
        from article_extractor import fetcher as fetcher_module

        network = NetworkOptions(user_agent="Sentinel-UA")
        result = fetcher_module._select_user_agent(network, "Fallback-UA")

        assert result == "Sentinel-UA"

    def test_select_user_agent_uses_randomized_value(self, monkeypatch):
        from article_extractor import fetcher as fetcher_module

        network = NetworkOptions(randomize_user_agent=True)
        monkeypatch.setattr(
            fetcher_module, "_generate_random_user_agent", lambda: "Random-UA"
        )

        assert fetcher_module._select_user_agent(network, "Fallback-UA") == "Random-UA"

    def test_select_user_agent_falls_back_when_random_missing(self, monkeypatch):
        from article_extractor import fetcher as fetcher_module

        network = NetworkOptions(randomize_user_agent=True)
        monkeypatch.setattr(fetcher_module, "_generate_random_user_agent", lambda: None)

        assert (
            fetcher_module._select_user_agent(network, "Fallback-UA") == "Fallback-UA"
        )


@pytest.mark.unit
class TestGenerateRandomUserAgent:
    def test_generate_random_user_agent_returns_value(self, monkeypatch):
        from article_extractor import fetcher as fetcher_module

        class DummyUA:
            @property
            def random(self):  # pragma: no cover - property is the behavior under test
                return "Agent/1.0"

        monkeypatch.setattr(fetcher_module, "_fake_useragent", DummyUA())

        assert fetcher_module._generate_random_user_agent() == "Agent/1.0"

    def test_generate_random_user_agent_handles_constructor_failure(
        self, monkeypatch, caplog
    ):
        from article_extractor import fetcher as fetcher_module

        class ExplodingUA:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("boom")

        fake_module = SimpleNamespace(UserAgent=ExplodingUA)
        monkeypatch.setitem(sys.modules, "fake_useragent", fake_module)
        monkeypatch.setattr(fetcher_module, "_fake_useragent", None)
        monkeypatch.setattr(fetcher_module, "_fake_useragent_error_logged", False)

        caplog.set_level("WARNING")
        assert fetcher_module._generate_random_user_agent() is None
        assert any("fake-useragent unavailable" in msg for msg in caplog.messages)

    def test_generate_random_user_agent_returns_none_after_error_logged(
        self, monkeypatch
    ):
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_fake_useragent", None)
        monkeypatch.setattr(fetcher_module, "_fake_useragent_error_logged", True)

        assert fetcher_module._generate_random_user_agent() is None


@pytest.mark.unit
class TestPlaywrightStorageStateFile:
    def test_storage_state_file_prefers_override(self, tmp_path):
        from article_extractor import PlaywrightFetcher

        override = tmp_path / "override.json"
        fetcher = PlaywrightFetcher(storage_state_file=override)

        assert fetcher.storage_state_file == override

    def test_storage_state_file_uses_network_path(self, tmp_path):
        from article_extractor import PlaywrightFetcher

        network_path = tmp_path / "network.json"
        network = NetworkOptions(storage_state_path=network_path)
        fetcher = PlaywrightFetcher(network=network)

        assert fetcher.storage_state_file == network_path

    def test_storage_state_file_defaults_via_network_resolver(
        self, tmp_path, monkeypatch
    ):
        from article_extractor import PlaywrightFetcher
        from article_extractor import fetcher as fetcher_module

        default_path = tmp_path / "default.json"

        def _fake_resolver(**_kwargs):
            return NetworkOptions(storage_state_path=default_path)

        monkeypatch.setattr(fetcher_module, "resolve_network_options", _fake_resolver)

        fetcher = PlaywrightFetcher()

        assert fetcher.storage_state_file == default_path
