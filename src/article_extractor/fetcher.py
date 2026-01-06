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
from typing import Any, Protocol
from urllib.parse import urlparse

from .network import host_matches_no_proxy, resolve_network_options
from .observability import build_url_log_context
from .storage_queue import (
    QueueStats,
    StorageQueue,
    StorageSnapshot,
    capture_snapshot,
    compute_fingerprint,
    normalize_payload,
)
from .types import NetworkOptions

logger = logging.getLogger(__name__)


def _augment_context(context: dict[str, str], **extra: Any) -> dict[str, Any]:
    if not context and not extra:
        return {}
    merged: dict[str, Any] = dict(context)
    for key, value in extra.items():
        if value is not None:
            merged[key] = value
    return merged


DEFAULT_DESKTOP_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_fake_useragent = None
_fake_useragent_error_logged = False


def _select_user_agent(network: NetworkOptions | None, fallback: str) -> str:
    """Choose a user agent honoring explicit and randomization settings."""

    if network and network.user_agent:
        logger.debug("Using explicit user agent override: %s", network.user_agent)
        return network.user_agent
    if network and network.randomize_user_agent:
        random_value = _generate_random_user_agent()
        if random_value:
            logger.debug("Randomized user agent selected: %s", random_value)
            return random_value
        logger.debug("Random user agent requested but generation failed; falling back")
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
            logger.debug("Playwright import succeeded; fetcher available")
        except ImportError:
            _playwright_available = False
            logger.debug("Playwright import failed; fetcher unavailable")
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

    MAX_CONCURRENT_PAGES = 3

    __slots__ = (
        "_browser",
        "_context",
        "_diagnostics_enabled",
        "_network",
        "_playwright",
        "_semaphore",
        "_storage_lock",
        "_storage_queue",
        "_storage_snapshot",
        "_storage_state_override",
        "_worker_token",
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
        diagnostics_enabled: bool = False,
    ) -> None:
        """Initialize Playwright fetcher.

        Args:
            headless: Whether to run browser in headless mode
            timeout: Page load timeout in milliseconds (default: 30s)
        """
        resolved_network = network or resolve_network_options()
        self._network = resolved_network
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
            else None
        )
        self._diagnostics_enabled = diagnostics_enabled
        self._storage_queue = self._initialize_storage_queue()
        self._storage_snapshot = None
        self._storage_lock: asyncio.Lock | None = None
        self._worker_token = f"playwright-{os.getpid()}-{id(self)}"

    def _log_diagnostic(
        self,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
        level: int = logging.INFO,
    ) -> None:
        if not self._diagnostics_enabled:
            return
        logger.log(level, message, extra=extra)

    def _initialize_storage_queue(self) -> StorageQueue | None:
        queue_kwargs: dict[str, Any] = {}
        try:  # Lazy import keeps fetcher usable without settings module
            from .settings import get_settings
        except Exception:  # pragma: no cover - settings always importable in repo
            settings = None
        else:
            settings = get_settings()
        if settings is not None:
            queue_kwargs = {
                "queue_dir": settings.storage_queue_dir,
                "max_entries": settings.storage_queue_max_entries,
                "max_age_seconds": settings.storage_queue_max_age_seconds,
                "processed_retention_seconds": settings.storage_queue_retention_seconds,
            }
        storage_file = self.storage_state_file
        if storage_file is None:
            return None

        try:
            return StorageQueue(storage_file, **queue_kwargs)
        except Exception as exc:  # pragma: no cover - best-effort fallback
            logger.warning(
                "Storage queue unavailable; falling back to direct writes",
                extra={
                    "storage_state": str(storage_file),
                    "error": exc.__class__.__name__,
                },
            )
            return None

    def _log_storage_state(self, stage: str) -> None:
        if not self._diagnostics_enabled:
            return
        storage_file = self.storage_state_file
        if storage_file is None:
            self._log_diagnostic(
                "Playwright storage disabled",
                extra={
                    "diagnostics_stage": stage,
                    "storage_enabled": False,
                    "headed": not self.headless,
                },
            )
            return
        metadata: dict[str, Any] = {
            "storage_state": str(storage_file),
            "storage_exists": storage_file.exists(),
            "diagnostics_stage": stage,
            "headed": not self.headless,
        }
        if storage_file.exists():
            try:
                stats = storage_file.stat()
                metadata.update(
                    {
                        "storage_bytes": stats.st_size,
                        "storage_mtime": int(stats.st_mtime),
                    }
                )
            except OSError as exc:
                metadata["storage_error"] = exc.__class__.__name__
        self._log_diagnostic("Playwright storage state", extra=metadata)

    def _log_stability_summary(
        self,
        context: dict[str, str],
        *,
        checks: int,
        stabilized: bool,
        max_checks: int,
    ) -> None:
        if not self._diagnostics_enabled:
            return
        self._log_diagnostic(
            "Playwright stability summary",
            extra=_augment_context(
                context,
                stability_checks=checks,
                max_stability_checks=max_checks,
                stability_converged=stabilized,
                headed=not self.headless,
                wait_for_stability=True,
                user_interaction_timeout=self.user_interaction_timeout,
            ),
        )

    def _log_queue_stats(self, stats: QueueStats | None) -> None:
        if not self._diagnostics_enabled or stats is None:
            return
        self._log_diagnostic(
            "Playwright storage queue",
            extra={
                "queue_pending": stats.pending,
                "queue_oldest_age": stats.oldest_age,
                "queue_latest_change_id": stats.newest_change_id,
            },
        )

    async def _persist_storage_payload(self, payload: bytes) -> None:
        storage_file = self.storage_state_file
        if storage_file is None:
            self._log_diagnostic(
                "Skipped Playwright storage persistence (disabled)",
                extra={"storage_enabled": False},
            )
            return

        fingerprint = compute_fingerprint(payload)
        snapshot: StorageSnapshot | None = self._storage_snapshot
        if snapshot and snapshot.fingerprint == fingerprint:
            self._log_diagnostic(
                "Playwright storage unchanged",
                extra={
                    "storage_state": str(snapshot.path),
                    "fingerprint": fingerprint,
                },
            )
            return

        queue = self._storage_queue
        if queue is None or self._storage_lock is None:
            self._write_storage_direct(payload)
            self._storage_snapshot = StorageSnapshot(
                path=storage_file, fingerprint=fingerprint, size=len(payload)
            )
            return

        try:
            async with self._storage_lock:
                queue.enqueue(
                    payload,
                    fingerprint=fingerprint,
                    worker_id=self._worker_token,
                )
                stats = queue.merge()
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(
                "Failed to merge storage queue; falling back to direct write",
                extra={
                    "storage_state": str(storage_file),
                    "error": exc.__class__.__name__,
                },
            )
            self._write_storage_direct(payload)
            self._storage_snapshot = StorageSnapshot(
                path=storage_file, fingerprint=fingerprint, size=len(payload)
            )
            return

        self._log_queue_stats(stats)
        self._storage_snapshot = StorageSnapshot(
            path=storage_file, fingerprint=fingerprint, size=len(payload)
        )
        logger.info(
            "Persisted storage state via queue",
            extra={
                "storage_state": str(storage_file),
                "latest_change_id": stats.newest_change_id if stats else None,
            },
        )
        self._log_storage_state("save")

    def _write_storage_direct(self, payload: bytes) -> None:
        storage_file = self.storage_state_file
        if storage_file is None:
            self._log_diagnostic(
                "Skipped direct storage write (disabled)",
                extra={"storage_enabled": False},
            )
            return
        storage_file.parent.mkdir(parents=True, exist_ok=True)
        with storage_file.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        logger.info("Saved storage state to %s", storage_file)
        self._log_storage_state("save")

    @property
    def network(self) -> NetworkOptions:
        return self._network

    @property
    def storage_state_file(self) -> Path | None:
        if self._storage_state_override is not None:
            return Path(self._storage_state_override)
        if self._network.storage_state_path is not None:
            return Path(self._network.storage_state_path)
        return None

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
        selected_user_agent = _select_user_agent(
            self._network, DEFAULT_DESKTOP_USER_AGENT
        )
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": selected_user_agent,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        storage_file = self.storage_state_file
        storage_label: str
        if storage_file is None:
            self._storage_snapshot = None
            self._storage_lock = None
            self._log_storage_state("load")
            storage_label = "disabled"
            logger.info(
                "Playwright storage persistence disabled; starting with fresh context"
            )
        else:
            self._storage_snapshot = capture_snapshot(storage_file)
            self._storage_lock = asyncio.Lock()
            self._log_storage_state("load")
            if storage_file.exists():
                context_options["storage_state"] = str(storage_file)
                logger.info("Loading storage state from %s", storage_file)
            else:
                logger.info(
                    "No storage state file found at %s; starting fresh", storage_file
                )
            storage_label = str(storage_file)

        self._context = await self._browser.new_context(**context_options)
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_PAGES)

        logger.info(
            "Playwright context ready (headless=%s, user_agent=%s, proxy=%s, storage=%s)",
            self.headless,
            selected_user_agent,
            self._network.proxy or "disabled",
            storage_label,
        )

        logger.info(
            f"Playwright browser created (max {self.MAX_CONCURRENT_PAGES} concurrent pages)"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser and save state."""
        logger.info("Closing Playwright browser...")

        storage_configured = self.storage_state_file is not None

        # Save storage state before closing
        if self._context:
            if storage_configured:
                try:
                    payload = await self._context.storage_state()
                    await self._persist_storage_payload(normalize_payload(payload))
                except Exception as e:
                    logger.warning(f"Failed to save storage state: {e}")
            else:
                self._log_diagnostic(
                    "Skipping storage persistence on shutdown (disabled)",
                    extra={"storage_enabled": False},
                )

            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._semaphore = None
        self._storage_lock = None
        self._storage_snapshot = None
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

        context = build_url_log_context(url)
        async with self._semaphore:
            logger.info("Fetching with Playwright", extra=context)

            page = await self._context.new_page()

            try:
                logger.debug(
                    "Playwright navigating to page",
                    extra=_augment_context(
                        context,
                        wait_for_selector=wait_for_selector,
                        wait_for_stability=wait_for_stability,
                    ),
                )
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout
                )

                try:
                    if wait_for_selector:
                        await page.wait_for_selector(wait_for_selector, timeout=5000)

                    await self._maybe_wait_for_user(page)

                    if wait_for_stability:
                        previous_content = ""
                        checks_performed = 0
                        stabilized = False
                        for _ in range(max_stability_checks):
                            checks_performed += 1
                            await asyncio.sleep(0.5)
                            current_content = await page.content()
                            if current_content == previous_content:
                                logger.debug("Content stabilized", extra=context)
                                stabilized = True
                                break
                            previous_content = current_content
                        else:
                            logger.warning("Content never stabilized", extra=context)

                        self._log_stability_summary(
                            context,
                            checks=checks_performed,
                            stabilized=stabilized,
                            max_checks=max_stability_checks,
                        )
                        content = previous_content
                    else:
                        content = await page.content()

                    status_code = response.status if response else 200
                    logger.info(
                        "Fetched with Playwright",
                        extra=_augment_context(
                            context,
                            status_code=status_code,
                            content_length=len(content),
                        ),
                    )
                    return content, status_code

                except TimeoutError:
                    selector_msg = (
                        f" '{wait_for_selector}'" if wait_for_selector else ""
                    )
                    logger.warning(
                        f"Timed out waiting for selector{selector_msg}",
                        extra=_augment_context(
                            context,
                            selector=wait_for_selector,
                        ),
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
        if storage_file and storage_file.exists():
            storage_file.unlink()
            logger.warning("Deleted persistent storage state file")

    async def clear_cookies(self) -> None:
        """Clear all cookies."""
        if self._context:
            await self._context.clear_cookies()
            logger.info("Cleared all cookies")

        storage_file = self.storage_state_file
        if storage_file and storage_file.exists():
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
            logger.debug("httpx import succeeded; fetcher available")
        except ImportError:
            _httpx_available = False
            logger.debug("httpx import failed; fetcher unavailable")
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

    MAX_ATTEMPTS = 3

    __slots__ = (
        "_client",
        "_diagnostics_enabled",
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
        diagnostics_enabled: bool = False,
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
        self._diagnostics_enabled = diagnostics_enabled
        self._headers = dict(self.DEFAULT_HEADERS)
        self._headers["User-Agent"] = _select_user_agent(
            self._network, DEFAULT_DESKTOP_USER_AGENT
        )

    def _log_diagnostic(
        self,
        message: str,
        *,
        extra: dict[str, Any] | None = None,
        level: int = logging.INFO,
    ) -> None:
        if not self._diagnostics_enabled:
            return
        logger.log(level, message, extra=extra)

    @staticmethod
    def _should_retry_status(status_code: int) -> bool:
        if status_code >= 500:
            return True
        return status_code in {408, 429}

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(0.3 * attempt, 1.5)

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
        logger.info(
            "httpx client initialized (timeout=%.1fs, follow_redirects=%s, proxy=%s)",
            self.timeout,
            self.follow_redirects,
            self._network.proxy or "disabled",
        )
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

        context = build_url_log_context(url)
        proxy = self._network.proxy
        host = urlparse(url).hostname
        client = self._client
        routed_via_proxy = False
        if (
            proxy
            and self._proxy_client
            and not host_matches_no_proxy(host, self._network.proxy_bypass)
        ):
            client = self._proxy_client
            routed_via_proxy = True
            logger.debug(
                "Routing request via proxy",
                extra=_augment_context(context, proxy=proxy),
            )
        else:
            logger.debug("Routing request via direct connection", extra=context)

        attempt = 1
        response = None
        while True:
            try:
                response = await client.get(url)
            except Exception as exc:
                if attempt >= self.MAX_ATTEMPTS:
                    logger.exception("httpx fetch failed", extra=context)
                    raise
                self._log_diagnostic(
                    "httpx fetch exception",
                    extra=_augment_context(
                        context,
                        attempt=attempt,
                        max_attempts=self.MAX_ATTEMPTS,
                        exception=exc.__class__.__name__,
                        via_proxy=routed_via_proxy,
                    ),
                    level=logging.WARNING,
                )
                await asyncio.sleep(self._backoff_delay(attempt))
                attempt += 1
                continue

            if (
                response is not None
                and self._should_retry_status(response.status_code)
                and attempt < self.MAX_ATTEMPTS
            ):
                self._log_diagnostic(
                    "httpx retryable response",
                    extra=_augment_context(
                        context,
                        attempt=attempt,
                        max_attempts=self.MAX_ATTEMPTS,
                        status_code=response.status_code,
                        via_proxy=routed_via_proxy,
                    ),
                )
                await asyncio.sleep(self._backoff_delay(attempt))
                attempt += 1
                continue

            break

        if response is None:  # pragma: no cover - defensive safeguard
            raise RuntimeError("httpx fetch produced no response")

        self._log_diagnostic(
            "httpx fetch summary",
            extra=_augment_context(
                context,
                status_code=response.status_code,
                attempts=attempt,
                via_proxy=routed_via_proxy,
            ),
        )

        logger.info(
            "Fetched with httpx",
            extra=_augment_context(
                context,
                status_code=response.status_code,
                content_length=len(response.text),
                via_proxy=routed_via_proxy,
                attempts=attempt,
            ),
        )
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
        logger.info(
            "Default fetcher: Playwright (prefer_playwright=%s)", prefer_playwright
        )
        return PlaywrightFetcher
    if _check_httpx():
        logger.info(
            "Default fetcher: httpx (prefer_playwright=%s, playwright_available=%s)",
            prefer_playwright,
            _playwright_available,
        )
        return HttpxFetcher
    if _check_playwright():
        logger.info("Default fetcher fallback: Playwright only option available")
        return PlaywrightFetcher

    raise ImportError(
        "No fetcher available. Install one of:\n"
        "  pip install article-extractor[playwright]  # for Playwright\n"
        "  pip install article-extractor[httpx]       # for httpx\n"
        "  pip install article-extractor[all]         # for both"
    )
