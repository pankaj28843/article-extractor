"""HTML fetchers for article extraction.

Provides multiple fetcher implementations:
- PlaywrightFetcher: Headless browser with cookie persistence (handles Cloudflare)
- HttpxFetcher: Lightweight async HTTP client (fast, for simple sites)

Each fetcher is self-contained with no module-level state, allowing safe
parallel async usage.

Usage:
    # Playwright (handles bot protection)
    async with PlaywrightFetcher() as fetcher:
        html, status = await fetcher.fetch(url)

    # httpx (lightweight, fast)
    async with HttpxFetcher() as fetcher:
        html, status = await fetcher.fetch(url)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class Fetcher(Protocol):
    """Protocol for HTML fetchers."""

    async def fetch(self, url: str) -> tuple[str, int]:
        """Fetch URL and return (html, status_code)."""
        ...

    async def __aenter__(self) -> Fetcher:
        """Enter async context."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        ...


# =============================================================================
# Playwright Fetcher (handles Cloudflare, bot protection)
# =============================================================================

# Lazy import flag - no mutable module state
_playwright_available: bool | None = None


def _check_playwright() -> bool:
    """Check if playwright is available."""
    global _playwright_available
    if _playwright_available is None:
        try:
            import playwright.async_api  # noqa: F401

            _playwright_available = True
        except ImportError:
            _playwright_available = False
    return _playwright_available


class PlaywrightFetcher:
    """Playwright-based fetcher with instance-level browser management.

    Each PlaywrightFetcher instance manages its own browser lifecycle.
    For multiple fetches, reuse the same context manager instance.

    Features:
    - Instance-level browser (no shared global state)
    - Semaphore-limited concurrent pages (max 3)
    - Persistent storage state survives restarts
    - Human-like behavior (viewport, user agent, timing)
    - Handles Cloudflare and bot protection

    Example:
        async with PlaywrightFetcher() as fetcher:
            html1, status1 = await fetcher.fetch(url1)
            html2, status2 = await fetcher.fetch(url2)
    """

    STORAGE_STATE_FILE = Path(
        os.environ.get(
            "PLAYWRIGHT_STORAGE_STATE_FILE",
            ".playwright-storage-state/storage-state.json",
        )
    )

    MAX_CONCURRENT_PAGES = 3

    __slots__ = (
        "headless",
        "timeout",
        "_playwright",
        "_browser",
        "_context",
        "_semaphore",
    )

    def __init__(self, headless: bool = True, timeout: int = 30000) -> None:
        """Initialize Playwright fetcher.

        Args:
            headless: Whether to run browser in headless mode
            timeout: Page load timeout in milliseconds (default: 30s)
        """
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser = None
        self._context = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> PlaywrightFetcher:
        """Create browser instance for this fetcher."""
        if not _check_playwright():
            raise ImportError("playwright not installed. Install with: pip install article-extractor[playwright]")

        from playwright.async_api import async_playwright

        logger.info("Creating Playwright browser instance...")

        # Start Playwright
        self._playwright = await async_playwright().start()

        # Check for HTTP proxy
        http_proxy_key = next((k for k in os.environ if k.lower() == "http_proxy"), None)
        http_proxy = os.environ.get(http_proxy_key) if http_proxy_key else None

        # Launch browser
        launch_options = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }

        if http_proxy:
            launch_options["proxy"] = {"server": http_proxy}
            logger.info(f"Using proxy: {http_proxy}")

        self._browser = await self._playwright.chromium.launch(**launch_options)

        # Create context with realistic settings
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        if self.STORAGE_STATE_FILE.exists():
            context_options["storage_state"] = str(self.STORAGE_STATE_FILE)
            logger.info(f"Loading storage state from {self.STORAGE_STATE_FILE}")

        self._context = await self._browser.new_context(**context_options)
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_PAGES)

        logger.info(f"Playwright browser created (max {self.MAX_CONCURRENT_PAGES} concurrent pages)")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser and save state."""
        logger.info("Closing Playwright browser...")

        # Save storage state before closing
        if self._context:
            try:
                self.STORAGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=str(self.STORAGE_STATE_FILE))
                logger.info(f"Saved storage state to {self.STORAGE_STATE_FILE}")
            except Exception as e:
                logger.warning(f"Failed to save storage state: {e}")

            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._semaphore = None
        logger.info("Playwright browser closed")

    async def fetch(
        self,
        url: str,
        wait_for_selector: str | None = None,
        wait_for_stability: bool = True,
        max_stability_checks: int = 20,
    ) -> tuple[str, int]:
        """Fetch URL content using Playwright with content stability checking.

        Args:
            url: URL to fetch
            wait_for_selector: Optional CSS selector to wait for
            wait_for_stability: Wait until HTML stops changing (default: True)
            max_stability_checks: Maximum stability checks (default: 20 = 10s)

        Returns:
            Tuple of (html_content, status_code)
        """
        if not self._context or not self._semaphore:
            raise RuntimeError("PlaywrightFetcher not initialized (use 'async with')")

        async with self._semaphore:
            logger.info(f"Fetching {url} with Playwright...")

            page = await self._context.new_page()

            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                try:
                    if wait_for_selector:
                        await page.wait_for_selector(wait_for_selector, timeout=5000)

                    if wait_for_stability:
                        previous_content = ""
                        for _ in range(max_stability_checks):
                            await asyncio.sleep(0.5)
                            current_content = await page.content()
                            if current_content == previous_content:
                                logger.debug(f"Content stabilized for {url}")
                                break
                            previous_content = current_content
                        else:
                            logger.warning(f"Content never stabilized for {url}")
                        content = previous_content
                    else:
                        content = await page.content()

                    status_code = response.status if response else 200
                    logger.info(f"Fetched {url} (status: {status_code}, {len(content)} chars)")
                    return content, status_code

                except asyncio.TimeoutError:
                    selector_msg = f" '{wait_for_selector}'" if wait_for_selector else ""
                    logger.warning(f"Timed out waiting for selector{selector_msg} on {url}")
                    return await page.content(), 408

            finally:
                await page.close()

    async def clear_storage_state(self) -> None:
        """Clear all storage state.

        ⚠️ WARNING: Use this method VERY sparingly!
        Clearing storage makes the browser look MORE like a bot.
        """
        if self._context:
            await self._context.clear_cookies()
            pages = self._context.pages
            for page in pages:
                with contextlib.suppress(Exception):
                    await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
            logger.warning("Cleared all storage state - browser now looks LESS like a real user!")

        if self.STORAGE_STATE_FILE.exists():
            self.STORAGE_STATE_FILE.unlink()
            logger.warning("Deleted persistent storage state file")

    async def clear_cookies(self) -> None:
        """Clear all cookies."""
        if self._context:
            await self._context.clear_cookies()
            logger.info("Cleared all cookies")

        if self.STORAGE_STATE_FILE.exists():
            self.STORAGE_STATE_FILE.unlink()
            logger.info("Deleted persistent storage state file")


# =============================================================================
# httpx Fetcher (lightweight, fast)
# =============================================================================

_httpx_available: bool | None = None


def _check_httpx() -> bool:
    """Check if httpx is available."""
    global _httpx_available
    if _httpx_available is None:
        try:
            import httpx  # noqa: F401

            _httpx_available = True
        except ImportError:
            _httpx_available = False
    return _httpx_available


class HttpxFetcher:
    """Lightweight async HTTP fetcher using httpx.

    Best for sites that don't have bot protection.
    Much faster than Playwright but can't handle JavaScript.

    Example:
        async with HttpxFetcher() as fetcher:
            html, status = await fetcher.fetch(url)
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    __slots__ = ("timeout", "follow_redirects", "_client")

    def __init__(self, timeout: float = 30.0, follow_redirects: bool = True) -> None:
        """Initialize httpx fetcher.

        Args:
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
        """
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self._client = None

    async def __aenter__(self) -> HttpxFetcher:
        """Create httpx client."""
        if not _check_httpx():
            raise ImportError("httpx not installed. Install with: pip install article-extractor[httpx]")

        import httpx

        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
            headers=self.DEFAULT_HEADERS,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch(self, url: str) -> tuple[str, int]:
        """Fetch URL content using httpx.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html_content, status_code)
        """
        if not self._client:
            raise RuntimeError("HttpxFetcher not initialized (use 'async with')")

        response = await self._client.get(url)
        return response.text, response.status_code


# =============================================================================
# Auto-select fetcher based on availability
# =============================================================================


def get_default_fetcher(
    prefer_playwright: bool = True,
) -> type[PlaywrightFetcher] | type[HttpxFetcher]:
    """Get the best available fetcher class.

    Args:
        prefer_playwright: Prefer Playwright if available (handles more sites)

    Returns:
        Fetcher class (PlaywrightFetcher or HttpxFetcher)

    Raises:
        ImportError: If no fetcher is available
    """
    if prefer_playwright and _check_playwright():
        return PlaywrightFetcher
    if _check_httpx():
        return HttpxFetcher
    if _check_playwright():
        return PlaywrightFetcher

    raise ImportError(
        "No fetcher available. Install one of:\n"
        "  pip install article-extractor[playwright]  # for Playwright\n"
        "  pip install article-extractor[httpx]       # for httpx\n"
        "  pip install article-extractor[all]         # for both"
    )
