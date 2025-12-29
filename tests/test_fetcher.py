"""Unit tests for article_extractor.fetcher module.

Following Cosmic Python's principle: "Building a Fake Repository for Tests Is Now Trivial!"
We mock external dependencies (playwright, httpx) to test the fetcher logic in isolation.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        page.content = AsyncMock(side_effect=["<html>content</html>", "<html>content</html>"])

        with patch("asyncio.sleep", AsyncMock()):
            content, status = await fetcher.fetch("https://example.com", wait_for_selector="#app")

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

        content, status = await fetcher.fetch("https://example.com", wait_for_stability=False)

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
        content, status = await fetcher.fetch("https://example.com", wait_for_selector="#slow")

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
            content, status = await fetcher.fetch("https://example.com", wait_for_stability=True)

        assert status == 200


@pytest.mark.unit
@pytest.mark.asyncio
class TestPlaywrightFetcherStorageState:
    """Test storage state management."""

    async def test_clear_storage_state(self, tmp_path, monkeypatch):
        """clear_storage_state should flush cookies, localStorage, and disk cache."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        context = AsyncMock()
        page_one = AsyncMock()
        page_two = AsyncMock()
        context.pages = [page_one, page_two]
        fetcher._context = context

        storage_file = tmp_path / "state.json"
        storage_file.write_text("data", encoding="utf-8")
        monkeypatch.setattr(PlaywrightFetcher, "STORAGE_STATE_FILE", storage_file)

        await fetcher.clear_storage_state()

        context.clear_cookies.assert_awaited_once()
        assert page_one.evaluate.await_count == 1
        assert page_two.evaluate.await_count == 1
        assert not storage_file.exists()

    async def test_clear_cookies(self, tmp_path, monkeypatch):
        """clear_cookies should clear cookies and delete storage file."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        fetcher._context = AsyncMock()

        storage_file = tmp_path / "cookies.json"
        storage_file.write_text("cookies", encoding="utf-8")
        monkeypatch.setattr(PlaywrightFetcher, "STORAGE_STATE_FILE", storage_file)

        await fetcher.clear_cookies()

        fetcher._context.clear_cookies.assert_awaited_once()
        assert not storage_file.exists()


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
