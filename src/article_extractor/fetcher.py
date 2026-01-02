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
from urllib.parse import urlparse

from .network import DEFAULT_STORAGE_PATH, STORAGE_ENV_KEYS, host_matches_no_proxy
from .types import NetworkOptions

logger = logging.getLogger(__name__)

DEFAULT_DESKTOP_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_fake_useragent = None
_fake_useragent_error_logged = False


def _select_user_agent(network: NetworkOptions | None, fallback: str) -> str:
    """Choose a user agent honoring explicit and randomization settings."""

    if network and network.user_agent:
        return network.user_agent
    if network and network.randomize_user_agent:
        random_value = _generate_random_user_agent()
        if random_value:
            return random_value
    return fallback


def _generate_random_user_agent() -> str | None:
    """Best-effort random desktop user agent string."""

    global _fake_useragent, _fake_useragent_error_logged

    if _fake_useragent is None and not _fake_useragent_error_logged:
        try:
            from fake_useragent import UserAgent

            _fake_useragent = UserAgent(browsers=["chrome", "firefox"])
        except Exception as exc:  # pragma: no cover - best-effort logging
            _fake_useragent_error_logged = True
            logger.warning("fake-useragent unavailable: %s", exc)
            return None

    if _fake_useragent is None:
        return None

    try:
        return _fake_useragent.random
    except Exception as exc:  # pragma: no cover - best-effort logging
        logger.warning("fake-useragent failed to generate UA: %s", exc)
        return None


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


def _detect_storage_state_file() -> Path:
    for key in STORAGE_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return Path(value).expanduser()
    return DEFAULT_STORAGE_PATH


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

    STORAGE_STATE_FILE = _detect_storage_state_file()
    _INITIAL_STORAGE_STATE_FILE = STORAGE_STATE_FILE

    MAX_CONCURRENT_PAGES = 3

    __slots__ = (
        "_browser",
        "_context",
        "_network",
        "_playwright",
        "_semaphore",
        "_storage_state_override",
        "headless",
        "timeout",
        "user_interaction_timeout",
    )

    def __init__(
        self,
        headless: bool | None = None,
        timeout: int = 30000,
        *,
        network: NetworkOptions | None = None,
        storage_state_file: str | Path | None = None,
    ) -> None:
        """Initialize Playwright fetcher.

        Args:
            headless: Whether to run browser in headless mode
            timeout: Page load timeout in milliseconds (default: 30s)
        """
        self._network = network or NetworkOptions()
        network_headed = self._network.headed
        self.headless = headless if headless is not None else not network_headed
        self.user_interaction_timeout = self._network.user_interaction_timeout
        self.timeout = timeout
        self._playwright = None
        self._browser = None
        self._context = None
        self._semaphore: asyncio.Semaphore | None = None
        self._storage_state_override = (
            Path(storage_state_file).expanduser()
            if storage_state_file is not None
            else self._network.storage_state_path
        )

    @property
    def network(self) -> NetworkOptions:
        return self._network

    @property
    def storage_state_file(self) -> Path:
        if self._storage_state_override is not None:
            return Path(self._storage_state_override)
        if self._network.storage_state_path is not None:
            return Path(self._network.storage_state_path)
        if self.STORAGE_STATE_FILE != self._INITIAL_STORAGE_STATE_FILE:
            return Path(self.STORAGE_STATE_FILE)
        return _detect_storage_state_file()

    async def __aenter__(self) -> PlaywrightFetcher:
        """Create browser instance for this fetcher."""
        if not _check_playwright():
            raise ImportError(
                "playwright not installed. Install with: pip install article-extractor[playwright]"
            )

        from playwright.async_api import async_playwright

        logger.info("Creating Playwright browser instance...")

        # Start Playwright
        self._playwright = await async_playwright().start()

        # Launch browser
        launch_options = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }

        if self._network.proxy:
            launch_options["proxy"] = {"server": self._network.proxy}
            logger.info("Using Playwright proxy: %s", self._network.proxy)

        self._browser = await self._playwright.chromium.launch(**launch_options)

        # Create context with realistic settings
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": _select_user_agent(self._network, DEFAULT_DESKTOP_USER_AGENT),
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        storage_file = self.storage_state_file
        if storage_file.exists():
            context_options["storage_state"] = str(storage_file)
            logger.info("Loading storage state from %s", storage_file)

        self._context = await self._browser.new_context(**context_options)
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_PAGES)

        logger.info(
            f"Playwright browser created (max {self.MAX_CONCURRENT_PAGES} concurrent pages)"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser and save state."""
        logger.info("Closing Playwright browser...")

        # Save storage state before closing
        if self._context:
            try:
                storage_file = self.storage_state_file
                storage_file.parent.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=str(storage_file))
                logger.info("Saved storage state to %s", storage_file)
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
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout
                )

                try:
                    if wait_for_selector:
                        await page.wait_for_selector(wait_for_selector, timeout=5000)

                    await self._maybe_wait_for_user(page)

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
                    logger.info(
                        f"Fetched {url} (status: {status_code}, {len(content)} chars)"
                    )
                    return content, status_code

                except TimeoutError:
                    selector_msg = (
                        f" '{wait_for_selector}'" if wait_for_selector else ""
                    )
                    logger.warning(
                        f"Timed out waiting for selector{selector_msg} on {url}"
                    )
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
                    await page.evaluate(
                        "() => { localStorage.clear(); sessionStorage.clear(); }"
                    )
            logger.warning(
                "Cleared all storage state - browser now looks LESS like a real user!"
            )

        storage_file = self.storage_state_file
        if storage_file.exists():
            storage_file.unlink()
            logger.warning("Deleted persistent storage state file")

    async def clear_cookies(self) -> None:
        """Clear all cookies."""
        if self._context:
            await self._context.clear_cookies()
            logger.info("Cleared all cookies")

        storage_file = self.storage_state_file
        if storage_file.exists():
            storage_file.unlink()
            logger.info("Deleted persistent storage state file")

    async def _maybe_wait_for_user(self, _page) -> None:
        """Allow human interaction when headed mode is enabled."""

        if self.headless or self.user_interaction_timeout <= 0:
            return

        remaining = float(self.user_interaction_timeout)
        logger.info(
            "Headed mode active; waiting up to %.1fs for manual interaction",
            remaining,
        )
        interval = 0.5
        while remaining > 0:
            await asyncio.sleep(min(interval, remaining))
            remaining -= interval


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
        "User-Agent": DEFAULT_DESKTOP_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    __slots__ = (
        "_client",
        "_headers",
        "_network",
        "_proxy_client",
        "follow_redirects",
        "timeout",
    )

    def __init__(
        self,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        *,
        network: NetworkOptions | None = None,
    ) -> None:
        """Initialize httpx fetcher.

        Args:
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
        """
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self._client = None
        self._proxy_client = None
        self._network = network or NetworkOptions()
        self._headers = dict(self.DEFAULT_HEADERS)
        self._headers["User-Agent"] = _select_user_agent(
            self._network, DEFAULT_DESKTOP_USER_AGENT
        )

    async def __aenter__(self) -> HttpxFetcher:
        """Create httpx client."""
        if not _check_httpx():
            raise ImportError(
                "httpx not installed. Install with: pip install article-extractor[httpx]"
            )

        import httpx

        def _build_client(**extra_kwargs):
            return httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                headers=self._headers.copy(),
                trust_env=False,
                **extra_kwargs,
            )

        self._client = _build_client()
        if self._network.proxy:
            self._proxy_client = _build_client(proxies=self._network.proxy)
        else:
            self._proxy_client = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close httpx client."""
        for attr in ("_client", "_proxy_client"):
            client = getattr(self, attr)
            if client:
                await client.aclose()
                setattr(self, attr, None)

    async def fetch(self, url: str) -> tuple[str, int]:
        """Fetch URL content using httpx.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html_content, status_code)
        """
        if not self._client:
            raise RuntimeError("HttpxFetcher not initialized (use 'async with')")

        proxy = self._network.proxy
        host = urlparse(url).hostname
        client = self._client
        if (
            proxy
            and self._proxy_client
            and not host_matches_no_proxy(host, self._network.proxy_bypass)
        ):
            client = self._proxy_client

        response = await client.get(url)
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
