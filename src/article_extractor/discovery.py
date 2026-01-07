"""Link discovery crawler powered by JustHTML.

Provides adaptive, polite crawling for documentation sites without
embedding extraction or storage logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

from justhtml import JustHTML

from .network import resolve_network_options
from .types import NetworkOptions

logger = logging.getLogger(__name__)


@dataclass
class RateLimitEvent:
    """Tracks a rate limit event for adaptive backoff."""

    timestamp: float
    host: str
    status_code: int
    was_success: bool


@dataclass
class HostRateLimitState:
    """Tracks rate limiting state for a specific host."""

    host: str
    base_delay: float = 2.0
    current_delay: float = 2.0
    min_delay: float = 0.5
    max_delay: float = 120.0
    consecutive_429s: int = 0
    consecutive_successes: int = 0
    total_429s: int = 0
    total_requests: int = 0
    last_429_time: float = 0.0
    events: deque = field(default_factory=lambda: deque(maxlen=100))

    def record_success(self) -> None:
        self.consecutive_429s = 0
        self.consecutive_successes += 1
        self.total_requests += 1
        self.events.append(
            RateLimitEvent(
                timestamp=time.time(),
                host=self.host,
                status_code=200,
                was_success=True,
            )
        )

        if self.consecutive_successes >= 10:
            self.current_delay = max(self.min_delay, self.current_delay * 0.9)
            self.consecutive_successes = 0
            logger.debug(
                "[%s] Reduced delay to %.2fs after successful streak",
                self.host,
                self.current_delay,
            )

    def record_429(self) -> None:
        now = time.time()
        self.consecutive_successes = 0
        self.consecutive_429s += 1
        self.total_429s += 1
        self.total_requests += 1
        self.events.append(
            RateLimitEvent(
                timestamp=now,
                host=self.host,
                status_code=429,
                was_success=False,
            )
        )

        time_since_last_429 = (
            now - self.last_429_time if self.last_429_time > 0 else float("inf")
        )
        self.last_429_time = now

        if time_since_last_429 < 30:
            multiplier = 2.0
        elif time_since_last_429 < 60:
            multiplier = 1.5
        else:
            multiplier = 1.25

        if self.consecutive_429s >= 3:
            multiplier *= 1.5

        old_delay = self.current_delay
        self.current_delay = min(self.max_delay, self.current_delay * multiplier)

        logger.warning(
            "[%s] 429 received! Delay: %.2fs -> %.2fs (consecutive: %s, total: %s, time_since_last: %.1fs)",
            self.host,
            old_delay,
            self.current_delay,
            self.consecutive_429s,
            self.total_429s,
            time_since_last_429,
        )

    def get_recent_429_rate(self, window_seconds: float = 300) -> float:
        now = time.time()
        cutoff = now - window_seconds
        recent_events = [e for e in self.events if e.timestamp > cutoff]
        if not recent_events:
            return 0.0
        rate_limit_events = [e for e in recent_events if e.status_code == 429]
        return len(rate_limit_events) / len(recent_events)

    def get_delay(self) -> float:
        import secrets

        rng = secrets.SystemRandom()
        jitter = rng.uniform(0.8, 1.2)
        return self.current_delay * jitter


class AdaptiveRateLimiter:
    """Manages per-host adaptive rate limiting."""

    def __init__(self, default_delay: float = 2.0):
        self.default_delay = default_delay
        self._host_states: dict[str, HostRateLimitState] = {}
        self._lock = asyncio.Lock()

    def _get_host_state(self, host: str) -> HostRateLimitState:
        if host not in self._host_states:
            self._host_states[host] = HostRateLimitState(
                host=host,
                base_delay=self.default_delay,
                current_delay=self.default_delay,
            )
        return self._host_states[host]

    def record_success(self, url: str) -> None:
        host = urlparse(url).netloc
        state = self._get_host_state(host)
        state.record_success()

    def record_429(self, url: str) -> None:
        host = urlparse(url).netloc
        state = self._get_host_state(host)
        state.record_429()

    def get_delay(self, url: str) -> float:
        host = urlparse(url).netloc
        state = self._get_host_state(host)
        return state.get_delay()

    async def wait(self, url: str, last_request_time: float) -> float:
        async with self._lock:
            current_time = time.time()
            delay = self.get_delay(url)
            time_since_last = current_time - last_request_time

            if time_since_last < delay:
                sleep_time = delay - time_since_last
                logger.debug(
                    "Rate limiting: sleeping for %.2fs (adaptive delay: %.2fs)",
                    sleep_time,
                    delay,
                )
                await asyncio.sleep(sleep_time)

            return time.time()

    def get_stats(self) -> dict[str, dict[str, float]]:
        return {
            host: {
                "current_delay": state.current_delay,
                "total_429s": state.total_429s,
                "total_requests": state.total_requests,
                "recent_429_rate": state.get_recent_429_rate(),
            }
            for host, state in self._host_states.items()
        }


class AdaptiveConcurrencyLimiter:
    """Dynamically adjusts crawler worker concurrency based on host feedback."""

    def __init__(self, min_limit: int, max_limit: int):
        self._min_limit = max(1, min_limit)
        self._max_limit = max(self._min_limit, max_limit)
        self._limit = self._min_limit
        self._peak_limit = self._limit
        self._active = 0
        self._peak_active = 0
        self._success_streak = 0
        self._last_rate_limit_at = 0.0
        self._condition = asyncio.Condition()

    async def acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self._active < self._limit)
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)

    async def release(self) -> None:
        async with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    async def record_success(self) -> None:
        async with self._condition:
            self._success_streak += 1
            window_clear = (time.time() - self._last_rate_limit_at) >= 60
            if (
                self._limit < self._max_limit
                and self._success_streak >= 25
                and window_clear
            ):
                self._limit += 1
                self._peak_limit = max(self._peak_limit, self._limit)
                self._success_streak = 0
                self._condition.notify_all()

    async def record_rate_limit(self) -> None:
        async with self._condition:
            new_limit = max(self._min_limit, self._limit // 2)
            self._limit = min(self._limit, new_limit)
            self._success_streak = 0
            self._last_rate_limit_at = time.time()
            self._condition.notify_all()

    def snapshot(self) -> dict[str, int]:
        return {
            "current_limit": self._limit,
            "peak_limit": self._peak_limit,
            "active_workers": self._active,
            "peak_active": self._peak_active,
        }


@dataclass
class CrawlConfig:
    """Configuration for crawler behavior."""

    user_agent: str = ""
    user_agent_provider: Callable[[], str] | None = None
    timeout: int = 30
    delay_seconds: float = 2.0
    max_pages: int | None = None
    same_host_only: bool = True
    allow_querystrings: bool = False
    max_retries: int = 3
    progress_interval: int = 10
    on_url_discovered: Callable[[str], None] | None = None
    headless: bool = True
    skip_recently_visited: Callable[[str], bool] | None = None
    force_crawl: bool = False
    markdown_url_suffix: str | None = None
    min_concurrency: int | None = None
    max_concurrency: int | None = None
    max_sessions: int | None = None
    prefer_playwright: bool = True
    should_process_url: Callable[[str], bool] | None = None
    network: NetworkOptions | None = None
    cookie_storage_dir: Path | None = None


@dataclass
class PageProcessResult:
    """Outcome of processing a single page."""

    success: bool
    rate_limited: bool = False


class EfficientCrawler:
    """BFS crawler optimized for discovery in docs sites."""

    def __init__(
        self,
        start_urls: set[str],
        crawl_config: CrawlConfig | None = None,
    ):
        self.start_urls = start_urls
        self.config = crawl_config or CrawlConfig()

        self.visited: set[str] = set()
        self._scheduled: set[str] = set()
        self.collected: set[str] = set()
        self.output_collected: set[str] = set()
        self._normalized_seed_urls: set[str] = set()
        self._markdown_url_suffix = (self.config.markdown_url_suffix or "").strip()

        self.frontier: deque[str] = deque()
        self._url_queue: asyncio.Queue[str] | None = None
        self._concurrency: AdaptiveConcurrencyLimiter | None = None
        self._stop_crawl = False

        self.client = None
        self._last_request_time: float = 0.0
        self._last_url: str | None = None
        self._rate_limiter = AdaptiveRateLimiter(
            default_delay=self.config.delay_seconds
        )

        self._crawler_skipped: int = 0

        self._cookies = None
        self._cookie_storage_key = f"crawler_cookies_{hash(tuple(sorted(start_urls)))}"

        self.allowed_hosts: set[str] = set()
        for url in start_urls:
            parsed = urlparse(url)
            self.allowed_hosts.add(parsed.netloc)

        logger.info("Initialized crawler with %s start URLs", len(start_urls))
        logger.info("Allowed hosts: %s", self.allowed_hosts)

    async def __aenter__(self):
        self.client = self._create_client()
        self._cookies = self.client.cookies if self.client else None
        await self._load_cookies()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._save_cookies()
        if self.client:
            await self.client.aclose()

    def _create_client(self):
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx not installed. Install with: pip install article-extractor[httpx]"
            ) from exc

        user_agent = self.config.user_agent
        if not user_agent and self.config.user_agent_provider:
            user_agent = self.config.user_agent_provider()
        if not user_agent:
            user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

        network = resolve_network_options(
            user_agent=user_agent, base=self.config.network
        )
        http_proxy = network.proxy

        transport = httpx.AsyncHTTPTransport(retries=self.config.max_retries)
        timeout = httpx.Timeout(self.config.timeout, connect=10.0)

        headers = {
            "User-Agent": user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "en,en-US;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
        }

        return httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
            verify=True,
            proxy=http_proxy if http_proxy else None,
        )

    def _get_cookie_file_path(self) -> Path:
        cookie_dir = self.config.cookie_storage_dir
        if cookie_dir is None:
            cookie_dir = (
                Path(tempfile.gettempdir()) / "article-extractor" / "crawler-cookies"
            )
        cookie_dir.mkdir(parents=True, exist_ok=True)
        return cookie_dir / f"{self._cookie_storage_key}.json"

    async def _load_cookies(self) -> None:
        if self._cookies is None:
            return
        import json

        cookie_file = self._get_cookie_file_path()

        try:
            if cookie_file.exists():
                cookie_data = json.loads(cookie_file.read_text()).get("cookies", {})
                for name, value in cookie_data.items():
                    if isinstance(value, dict):
                        self._cookies.set(
                            name=name,
                            value=value.get("value", ""),
                            domain=value.get("domain", ""),
                            path=value.get("path", "/"),
                        )
                    else:
                        self._cookies.set(name, value)

                logger.debug("Loaded %s cookies from filesystem", len(cookie_data))
        except Exception as exc:
            logger.debug("Failed to load cookies from filesystem: %s", exc)

    async def _save_cookies(self) -> None:
        if self._cookies is None:
            return
        import json

        cookie_file = self._get_cookie_file_path()

        try:
            cookie_data = {}
            for cookie in self._cookies.jar:
                cookie_data[cookie.name] = {
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "expires": cookie.expires,
                    "secure": cookie.secure,
                }

            document = {
                "cookies": cookie_data,
                "updated_at": time.time(),
                "url_set": list(self.start_urls)[:5],
            }

            cookie_file.write_text(json.dumps(document, indent=2))
            logger.debug("Saved %s cookies to filesystem", len(cookie_data))
        except Exception as exc:
            logger.debug("Failed to save cookies: %s", exc)

    async def crawl(self) -> set[str]:
        if not self.client:
            raise RuntimeError("Crawler must be used as async context manager")

        seed_urls = self._initialize_frontier()
        self.output_collected.clear()

        self._url_queue = asyncio.Queue()
        for url in seed_urls:
            self._url_queue.put_nowait(url)
        self._stop_crawl = False

        configured_min = self.config.min_concurrency or (len(seed_urls) or 1)
        configured_max = self.config.max_concurrency or configured_min
        max_sessions = self.config.max_sessions or configured_max
        worker_pool_size = max(1, min(max_sessions, configured_max))
        min_limit = max(1, min(configured_min, worker_pool_size))
        self._concurrency = AdaptiveConcurrencyLimiter(min_limit, worker_pool_size)

        logger.info(
            "Starting BFS crawl with %s seed URLs (workers=%s, min=%s, max=%s)",
            len(seed_urls),
            worker_pool_size,
            min_limit,
            worker_pool_size,
        )

        start_time = time.time()
        progress_lock = asyncio.Lock()
        progress_state = {"last_report": 0}

        workers = [
            asyncio.create_task(
                self._crawl_worker(start_time, progress_state, progress_lock)
            )
            for _ in range(worker_pool_size)
        ]

        await self._url_queue.join()
        for _ in workers:
            await self._url_queue.put(None)
        await asyncio.gather(*workers)

        self._url_queue = None
        self._concurrency = None
        self._stop_crawl = False

        self._log_completion(start_time)
        combined_results = set(self.collected)
        combined_results.update(self.output_collected)
        return combined_results

    def _initialize_frontier(self) -> list[str]:
        self.frontier.clear()
        self._scheduled.clear()
        deduped_seeds: set[str] = set()
        normalized_seeds: list[str] = []

        for url in sorted(self.start_urls):
            normalized = self._normalize_url(url)
            if not normalized:
                logger.warning("Failed to normalize: %s", url)
                continue

            if not self._should_process_url(normalized):
                logger.warning("Filtered out: %s", normalized)
                continue

            if normalized in deduped_seeds:
                continue

            deduped_seeds.add(normalized)
            normalized_seeds.append(normalized)

        for normalized in normalized_seeds:
            self.frontier.append(normalized)
            self._scheduled.add(normalized)
            logger.info("Added to frontier: %s", normalized)

        self._normalized_seed_urls = set(normalized_seeds)
        return normalized_seeds

    def _should_stop_crawl(self) -> bool:
        if self.config.max_pages and len(self.collected) >= self.config.max_pages:
            logger.info("Reached max_pages limit (%s)", self.config.max_pages)
            return True
        return False

    def _should_report_progress(self, last_report: int) -> bool:
        return len(self.collected) - last_report >= self.config.progress_interval

    def _report_progress(self, start_time: float) -> None:
        elapsed = time.time() - start_time
        rate = len(self.collected) / elapsed if elapsed > 0 else 0
        pending = len(self.frontier)
        if self._url_queue is not None:
            pending = self._url_queue.qsize()
        logger.info(
            "Progress: %s collected, %s in queue, %s visited (%.1f pages/sec)",
            len(self.collected),
            pending,
            len(self.visited),
            rate,
        )

    def _remove_from_frontier(self, url: str) -> None:
        if not self.frontier:
            return

        if self.frontier and self.frontier[0] == url:
            self.frontier.popleft()
            return

        with contextlib.suppress(ValueError):
            self.frontier.remove(url)

    async def _maybe_report_progress(
        self, start_time: float, progress_state: dict, progress_lock: asyncio.Lock
    ) -> None:
        async with progress_lock:
            if self._should_report_progress(progress_state["last_report"]):
                self._report_progress(start_time)
                progress_state["last_report"] = len(self.collected)

    def _log_completion(self, start_time: float) -> None:
        elapsed = time.time() - start_time
        rate = len(self.collected) / elapsed if elapsed > 0 else 0
        skipped_msg = (
            f", {self._crawler_skipped} skipped (recently visited)"
            if self._crawler_skipped > 0
            else ""
        )
        logger.info(
            "Crawl complete: %s pages collected in %.1fs (%.1f pages/sec)%s",
            len(self.collected),
            elapsed,
            rate,
            skipped_msg,
        )

        rate_stats = self._rate_limiter.get_stats()
        for host, stats in rate_stats.items():
            if stats["total_429s"] > 0:
                logger.info(
                    "Rate limit stats for %s: %s/%s requests were 429s, final delay: %.2fs",
                    host,
                    stats["total_429s"],
                    stats["total_requests"],
                    stats["current_delay"],
                )

    async def _crawl_worker(
        self, start_time: float, progress_state: dict, progress_lock: asyncio.Lock
    ) -> None:
        if self._url_queue is None or self._concurrency is None:
            raise RuntimeError("Crawler queue not initialized")

        while True:
            url = await self._url_queue.get()

            if url is None:
                self._url_queue.task_done()
                return

            await self._handle_crawl_url(url, start_time, progress_state, progress_lock)
            self._url_queue.task_done()

    async def _handle_crawl_url(
        self,
        url: str,
        start_time: float,
        progress_state: dict,
        progress_lock: asyncio.Lock,
    ) -> None:
        self._remove_from_frontier(url)

        if self._stop_crawl or self._should_stop_crawl():
            self._stop_crawl = True
            self._scheduled.discard(url)
            return

        if url in self.visited:
            self._scheduled.discard(url)
            return

        if self._should_skip_recent(url):
            self._record_skip(url)
            await self._maybe_report_progress(start_time, progress_state, progress_lock)
            return

        await self._concurrency.acquire()
        result: PageProcessResult | None = None
        should_requeue = False

        try:
            result = await self._process_page(url)
            if result and result.rate_limited and not result.success:
                should_requeue = True
        except Exception:
            logger.exception("Worker failed on %s", url)
        finally:
            if result:
                if result.rate_limited:
                    await self._concurrency.record_rate_limit()
                elif result.success:
                    await self._concurrency.record_success()

            if result and result.success:
                self.visited.add(url)

            await self._concurrency.release()

            if should_requeue:
                self.frontier.append(url)
                self._scheduled.add(url)
                await self._url_queue.put(url)
            else:
                self._scheduled.discard(url)

            await self._maybe_report_progress(start_time, progress_state, progress_lock)

    def _should_skip_recent(self, url: str) -> bool:
        return (
            (not self.config.force_crawl)
            and self.config.skip_recently_visited
            and self.config.skip_recently_visited(url)
        )

    def _record_skip(self, url: str) -> None:
        self._crawler_skipped += 1
        self.visited.add(url)
        self.collected.add(url)
        converted = self._convert_to_markdown_url(
            url, is_seed=url in self._normalized_seed_urls
        )
        self.output_collected.add(converted)
        self._scheduled.discard(url)

    @staticmethod
    def _coerce_fetch_result(
        result: str | None | tuple[str | None, bool],
    ) -> tuple[str | None, bool]:
        if isinstance(result, tuple) and len(result) == 2:
            content, rate_limited = result
            return content, bool(rate_limited)
        return result, False

    async def _process_page(self, url: str) -> PageProcessResult:  # noqa: PLR0912
        if self.client is None:
            raise RuntimeError("Crawler must be used within async context manager")

        await self._apply_rate_limit(url)

        headers = {}
        if self._last_url:
            headers["Referer"] = self._last_url

        if self.config.prefer_playwright:
            fetch_result = await self._fetch_with_playwright_first(
                url,
                headers,
                include_rate_limit=True,
            )
        else:
            fetch_result = await self._fetch_with_httpx_first(
                url,
                headers,
                include_rate_limit=True,
            )

        html_content, rate_limited = self._coerce_fetch_result(fetch_result)

        if html_content is None:
            logger.error("Failed to fetch content for %s", url)
            return PageProcessResult(success=False, rate_limited=rate_limited)

        self.collected.add(url)
        converted_current = self._convert_to_markdown_url(
            url, is_seed=url in self._normalized_seed_urls
        )
        self.output_collected.add(converted_current)
        self._last_url = url

        links = self._extract_links(html_content, url)
        queued = 0

        for link in links:
            normalized = self._normalize_url(link)
            if not normalized:
                continue

            if normalized in self.visited or normalized in self._scheduled:
                continue

            if not self._should_process_url(normalized):
                continue

            self.frontier.append(normalized)
            self._scheduled.add(normalized)
            if self._url_queue is not None:
                await self._url_queue.put(normalized)
            queued += 1

            converted_discovery = self._convert_to_markdown_url(
                normalized, is_seed=False
            )
            if self.config.on_url_discovered:
                try:
                    self.config.on_url_discovered(converted_discovery)
                except Exception as exc:
                    logger.warning(
                        "URL discovery callback failed for %s: %s",
                        converted_discovery,
                        exc,
                    )

        if queued > 0:
            logger.info("Queued %s new links from %s", queued, url)

        return PageProcessResult(success=True, rate_limited=rate_limited)

    async def _fetch_with_playwright_first(
        self,
        url: str,
        headers: dict,
        *,
        include_rate_limit: bool = False,
    ) -> str | None | tuple[str | None, bool]:
        if self.client is None:
            raise RuntimeError("Client must be initialized")
        import httpx

        content, rate_limited, fallback = await self._fetch_playwright(url)
        if not fallback:
            return self._format_fetch_result(content, rate_limited, include_rate_limit)

        try:
            response = await self.client.get(url, headers=headers)
            if response.status_code == 429:
                self._rate_limiter.record_429(url)
                return self._format_fetch_result(None, True, include_rate_limit)
            response.raise_for_status()
            self._rate_limiter.record_success(url)
            return self._format_fetch_result(response.text, False, include_rate_limit)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._rate_limiter.record_429(url)
                return self._format_fetch_result(None, True, include_rate_limit)
            logger.error("Both Playwright and httpx failed for %s: httpx=%s", url, exc)
        except Exception as http_error:
            logger.error(
                "Both Playwright and httpx failed for %s: httpx=%s", url, http_error
            )

        return self._format_fetch_result(None, rate_limited, include_rate_limit)

    async def _fetch_with_httpx_first(
        self,
        url: str,
        headers: dict,
        *,
        include_rate_limit: bool = False,
    ) -> str | None | tuple[str | None, bool]:
        if self.client is None:
            raise RuntimeError("Client must be initialized")
        content, rate_limited = await self._fetch_httpx_with_retries(url, headers)
        if content is not None or rate_limited:
            return self._format_fetch_result(content, rate_limited, include_rate_limit)

        content, rate_limited, _fallback = await self._fetch_playwright(url)
        return self._format_fetch_result(content, rate_limited, include_rate_limit)

    def _format_fetch_result(
        self,
        content: str | None,
        rate_limited: bool,
        include_rate_limit: bool,
    ) -> str | None | tuple[str | None, bool]:
        return (content, rate_limited) if include_rate_limit else content

    async def _fetch_playwright(self, url: str) -> tuple[str | None, bool, bool]:
        try:
            from .fetcher import PlaywrightFetcher

            network = resolve_network_options(
                user_agent=self.config.user_agent or None,
                base=self.config.network,
            )
            async with PlaywrightFetcher(
                headless=self.config.headless, network=network
            ) as fetcher:
                html_content, status_code = await fetcher.fetch(url)
                if status_code == 429:
                    self._rate_limiter.record_429(url)
                    delay = self._rate_limiter.get_delay(url)
                    logger.warning(
                        "Playwright got 429 for %s, backing off %.2fs", url, delay
                    )
                    await asyncio.sleep(delay)
                    return None, True, False
                self._rate_limiter.record_success(url)
                return html_content, False, False
        except OSError as os_error:
            if os_error.errno == 24:
                logger.warning(
                    "File descriptor exhaustion for %s, backing off 30s...", url
                )
                await asyncio.sleep(30)
                return None, False, False
            logger.warning(
                "Playwright failed for %s: %s, trying httpx...", url, os_error
            )
        except Exception as pw_error:
            logger.warning(
                "Playwright failed for %s: %s, trying httpx...", url, pw_error
            )

        return None, False, True

    async def _fetch_httpx_with_retries(
        self, url: str, headers: dict
    ) -> tuple[str | None, bool]:
        import httpx

        rate_limited = False
        max_retries = max(1, self.config.max_retries)
        for attempt in range(max_retries):
            try:
                response = await self.client.get(url, headers=headers)
                if response.status_code == 429:
                    self._rate_limiter.record_429(url)
                    rate_limited = True
                    delay = self._rate_limiter.get_delay(url)
                    logger.warning(
                        "httpx got 429 for %s, backing off %.2fs before retry %s",
                        url,
                        delay,
                        attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                self._rate_limiter.record_success(url)
                return response.text, rate_limited
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    self._rate_limiter.record_429(url)
                    rate_limited = True
                    delay = self._rate_limiter.get_delay(url)
                    logger.warning(
                        "httpx raised 429 for %s, backing off %.2fs before retry %s",
                        url,
                        delay,
                        attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
                if status_code in (403, 404, 503):
                    wait_time = (attempt + 1) * 5.0
                    logger.warning(
                        "httpx got %s for %s, waiting %.1fs before retry %s",
                        status_code,
                        url,
                        wait_time,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                logger.warning("HTTP status error for %s: %s", url, status_code)
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                delay = self.config.delay_seconds * (attempt + 1)
                logger.warning(
                    "Network error for %s (%s), retrying in %.2fs", url, exc, delay
                )
                await asyncio.sleep(delay)
            except Exception as http_error:
                logger.error("HTTP fetch failed for %s: %s", url, http_error)
                break

        return None, rate_limited

    def _extract_links(self, html: str, base_url: str) -> set[str]:
        try:
            doc = JustHTML(html)
            links: set[str] = set()

            for node in self._iter_nodes(doc.root):
                attrs = getattr(node, "attrs", None) or {}
                href = attrs.get("href")
                if isinstance(href, list):
                    href = href[0] if href else ""
                if isinstance(href, str) and href:
                    links.add(urljoin(base_url, href))

            return links
        except Exception as exc:
            logger.debug("Failed to extract links from %s: %s", base_url, exc)
            return set()

    def _iter_nodes(self, node):
        yield node
        for child in getattr(node, "children", []) or []:
            yield from self._iter_nodes(child)

    def _supports_markdown_suffix(self) -> bool:
        return bool(self._markdown_url_suffix)

    def _convert_to_markdown_url(self, url: str, *, is_seed: bool) -> str:
        if is_seed or not self._supports_markdown_suffix():
            return url

        try:
            parsed = urlparse(url)
            path = parsed.path or "/"
            trimmed_path = path.rstrip("/")
            if not trimmed_path:
                return url

            suffix = self._markdown_url_suffix
            if trimmed_path.endswith(suffix):
                markdown_path = trimmed_path
            else:
                last_segment = trimmed_path.split("/")[-1]
                if "." in last_segment:
                    _base, ext = last_segment.rsplit(".", 1)
                    if ext.lower() in {"html", "htm"}:
                        trimmed_path = trimmed_path[: -(len(ext) + 1)]
                    else:
                        return url
                markdown_path = f"{trimmed_path}{suffix}"

            normalized = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    markdown_path,
                    parsed.params,
                    parsed.query if self.config.allow_querystrings else "",
                    "",
                )
            )
            return normalized
        except Exception as exc:
            logger.debug("Failed to convert %s to markdown variant: %s", url, exc)
            return url

    def _normalize_url(self, url: str) -> str | None:
        try:
            url, _frag = urldefrag(url)
            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https"):
                return None

            query = parsed.query if self.config.allow_querystrings else ""
            path = parsed.path or "/"

            normalized = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    path,
                    parsed.params,
                    query,
                    "",
                )
            )

            return normalized

        except Exception as exc:
            logger.debug("Failed to normalize URL %s: %s", url, exc)
            return None

    def _should_process_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()

        non_html_extensions = {
            ".css",
            ".js",
            ".json",
            ".xml",
            ".txt",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
            ".webp",
            ".bmp",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".wav",
            ".flv",
            ".wmv",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".otf",
        }

        if any(path.endswith(ext) for ext in non_html_extensions):
            return False

        if self.config.should_process_url:
            return self.config.should_process_url(url)

        return True

    def _should_crawl_url(self, url: str) -> bool:
        parsed = urlparse(url)

        if self.config.same_host_only and parsed.netloc not in self.allowed_hosts:
            logger.debug(
                "Host check failed for %s: %s not in %s",
                url,
                parsed.netloc,
                self.allowed_hosts,
            )
            return False

        return True

    async def _apply_rate_limit(self, url: str | None = None) -> None:
        if self.config.delay_seconds > 0 and url:
            self._last_request_time = await self._rate_limiter.wait(
                url, self._last_request_time
            )
        elif self.config.delay_seconds > 0:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            if time_since_last < self.config.delay_seconds:
                await asyncio.sleep(self.config.delay_seconds - time_since_last)
            self._last_request_time = time.time()
