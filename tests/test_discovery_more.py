import asyncio
import secrets
from unittest.mock import AsyncMock

import httpx
import pytest

from article_extractor.discovery import (
    AdaptiveConcurrencyLimiter,
    AdaptiveRateLimiter,
    CrawlConfig,
    EfficientCrawler,
    HostRateLimitState,
    PageProcessResult,
)


class _SequenceClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def get(self, _url, headers=None):
        if not self._responses:
            raise AssertionError("No more responses configured")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _make_response(status_code, text="OK"):
    request = httpx.Request("GET", "https://example.com")
    return httpx.Response(status_code, text=text, request=request)


def test_initialize_frontier_filters_and_dedupes():
    config = CrawlConfig(should_process_url=lambda url: "skip" not in url)
    crawler = EfficientCrawler(
        {
            "https://example.com/keep",
            "https://example.com/skip",
            "ftp://example.com/ignore",
        },
        config,
    )

    seeds = crawler._initialize_frontier()

    assert seeds == ["https://example.com/keep"]
    assert crawler.frontier[0] == "https://example.com/keep"


def test_normalize_url_drops_fragments_and_queries():
    crawler = EfficientCrawler({"https://example.com"})

    normalized = crawler._normalize_url("https://example.com/path?x=1#frag")

    assert normalized == "https://example.com/path"
    assert crawler._normalize_url("mailto:test@example.com") is None


def test_convert_to_markdown_url_handles_suffixes():
    config = CrawlConfig(markdown_url_suffix=".md")
    crawler = EfficientCrawler({"https://example.com"}, config)

    html_url = "https://example.com/docs/page.html?x=1"
    assert (
        crawler._convert_to_markdown_url(html_url, is_seed=False)
        == "https://example.com/docs/page.md"
    )

    image_url = "https://example.com/assets/image.png"
    assert crawler._convert_to_markdown_url(image_url, is_seed=False) == image_url


def test_should_process_url_filters_extensions_and_custom():
    config = CrawlConfig(should_process_url=lambda url: "allow" in url)
    crawler = EfficientCrawler({"https://example.com"}, config)

    assert crawler._should_process_url("https://example.com/file.pdf") is False
    assert crawler._should_process_url("https://example.com/allow") is True
    assert crawler._should_process_url("https://example.com/deny") is False


def test_should_crawl_url_respects_host_limit():
    crawler = EfficientCrawler({"https://example.com"})

    assert crawler._should_crawl_url("https://example.com/docs") is True
    assert crawler._should_crawl_url("https://other.com/docs") is False


def test_record_skip_updates_outputs(tmp_path):
    config = CrawlConfig(markdown_url_suffix=".md", cookie_storage_dir=tmp_path)
    crawler = EfficientCrawler({"https://example.com/start"}, config)
    crawler._normalized_seed_urls = {"https://example.com/start"}

    crawler._record_skip("https://example.com/skip")

    assert "https://example.com/skip" in crawler.visited
    assert "https://example.com/skip" in crawler.collected
    assert "https://example.com/skip.md" in crawler.output_collected


@pytest.mark.asyncio
async def test_apply_rate_limit_without_url(monkeypatch):
    config = CrawlConfig(delay_seconds=0.5)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._last_request_time = 9.9

    times = iter([10.0, 10.5])
    monkeypatch.setattr(
        "article_extractor.discovery.time.time",
        lambda: next(times),
    )

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    await crawler._apply_rate_limit()

    assert crawler._last_request_time == 10.5


def test_extract_links_handles_parser_error(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = object()

    class _BrokenHTML:
        def __init__(self, _html):
            raise ValueError("boom")

    monkeypatch.setattr("article_extractor.discovery.JustHTML", _BrokenHTML)

    assert crawler._extract_links("<html></html>", "https://example.com") == set()


@pytest.mark.asyncio
async def test_fetch_httpx_with_retries_handles_rate_limits(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient(
        [
            _make_response(429, "rate limited"),
            _make_response(403, "forbidden"),
            _make_response(200, "ok"),
        ]
    )
    crawler.config.max_retries = 3
    crawler.config.delay_seconds = 0

    monkeypatch.setattr(crawler._rate_limiter, "get_delay", lambda _url: 0)

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    content, _rate_limited = await crawler._fetch_httpx_with_retries(
        "https://example.com", headers={}
    )

    assert content == "ok"
    assert _rate_limited is True


@pytest.mark.asyncio
async def test_fetch_with_httpx_first_short_circuits_on_rate_limit(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = object()

    async def _fake_httpx(_url, _headers):
        return None, True

    async def _boom(*_args, **_kwargs):
        raise AssertionError("Playwright fallback should not be called")

    monkeypatch.setattr(crawler, "_fetch_httpx_with_retries", _fake_httpx)
    monkeypatch.setattr(crawler, "_fetch_playwright", _boom)

    result = await crawler._fetch_with_httpx_first(
        "https://example.com", headers={}, include_rate_limit=True
    )

    assert result == (None, True)


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_falls_back_to_httpx(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient([_make_response(200, "ok")])

    async def _fake_playwright(_url):
        return None, False, True

    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_playwright_first(
        "https://example.com", headers={}, include_rate_limit=True
    )

    assert result == ("ok", False)


@pytest.mark.asyncio
async def test_fetch_playwright_handles_fd_exhaustion(monkeypatch):
    from article_extractor import fetcher as fetcher_module

    class _FailingFetcher:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            raise OSError(24, "Too many open files")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(fetcher_module, "PlaywrightFetcher", _FailingFetcher)

    crawler = EfficientCrawler({"https://example.com"})

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    content, _rate_limited, fallback = await crawler._fetch_playwright(
        "https://example.com"
    )

    assert content is None
    assert _rate_limited is False
    assert fallback is False


def test_cookie_round_trip(tmp_path):
    config = CrawlConfig(cookie_storage_dir=tmp_path)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._cookies = httpx.Cookies()
    crawler._cookies.set("session", "value", domain="example.com", path="/")

    asyncio.run(crawler._save_cookies())

    new_crawler = EfficientCrawler({"https://example.com"}, config)
    new_crawler._cookies = httpx.Cookies()
    asyncio.run(new_crawler._load_cookies())

    assert new_crawler._cookies.get("session") == "value"


def test_rate_limit_state_tracks_429s(monkeypatch):
    state = HostRateLimitState(host="example.com", current_delay=2.0)

    times = iter([10.0, 20.0])
    monkeypatch.setattr(
        "article_extractor.discovery.time.time",
        lambda: next(times),
    )

    state.record_429()

    assert state.total_429s == 1
    assert state.current_delay >= 2.0


def test_adaptive_rate_limiter_stats():
    limiter = AdaptiveRateLimiter(default_delay=1.5)

    limiter.record_success("https://example.com")
    limiter.record_429("https://example.com")

    stats = limiter.get_stats()

    assert "example.com" in stats
    assert stats["example.com"]["total_requests"] == 2


@pytest.mark.asyncio
async def test_concurrency_limiter_rate_limit_reduces_limit():
    limiter = AdaptiveConcurrencyLimiter(min_limit=1, max_limit=4)
    limiter._limit = 4

    await limiter.record_rate_limit()

    assert limiter.snapshot()["current_limit"] == 2


def test_should_stop_crawl_respects_max_pages():
    config = CrawlConfig(max_pages=1)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.collected.add("https://example.com/one")

    assert crawler._should_stop_crawl() is True


def test_should_report_progress_threshold():
    config = CrawlConfig(progress_interval=2)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.collected.update({"a", "b"})

    assert crawler._should_report_progress(0) is True


def test_remove_from_frontier_handles_middle_entry():
    crawler = EfficientCrawler({"https://example.com"})
    crawler.frontier.extend(["a", "b", "c"])

    crawler._remove_from_frontier("b")

    assert list(crawler.frontier) == ["a", "c"]


@pytest.mark.asyncio
async def test_maybe_report_progress_updates_state(monkeypatch):
    config = CrawlConfig(progress_interval=1)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.collected.add("a")
    progress_state = {"last_report": 0}
    progress_lock = asyncio.Lock()
    calls = {"count": 0}

    def _record(_start_time):
        calls["count"] += 1

    monkeypatch.setattr(crawler, "_report_progress", _record)

    await crawler._maybe_report_progress(0.0, progress_state, progress_lock)

    assert calls["count"] == 1
    assert progress_state["last_report"] == 1


@pytest.mark.asyncio
async def test_process_page_discovers_and_handles_callback_error(monkeypatch):
    def _boom(_url):
        raise ValueError("boom")

    config = CrawlConfig(prefer_playwright=False, on_url_discovered=_boom)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.client = object()
    crawler._normalized_seed_urls = {"https://example.com"}
    crawler._url_queue = asyncio.Queue()
    crawler.visited.add("https://example.com/already")

    async def _noop_rate_limit(_url=None):
        return None

    async def _fake_fetch(_url, _headers, include_rate_limit=False):
        return (
            "<html><a href='/next'></a><a href='https://example.com/already'></a></html>",
            False,
        )

    monkeypatch.setattr(crawler, "_apply_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(crawler, "_fetch_with_httpx_first", _fake_fetch)

    result = await crawler._process_page("https://example.com")

    assert result.success is True
    assert "https://example.com/next" in crawler._scheduled
    assert crawler._url_queue.qsize() == 1


@pytest.mark.asyncio
async def test_handle_crawl_url_requeues_on_rate_limit(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._concurrency = AdaptiveConcurrencyLimiter(min_limit=1, max_limit=1)
    crawler.frontier.append("https://example.com")
    crawler._scheduled.add("https://example.com")

    async def _fake_process(_url):
        return PageProcessResult(success=False, rate_limited=True)

    async def _noop_report(*_args, **_kwargs):
        return None

    monkeypatch.setattr(crawler, "_process_page", _fake_process)
    monkeypatch.setattr(crawler, "_maybe_report_progress", _noop_report)

    await crawler._handle_crawl_url(
        "https://example.com",
        start_time=0.0,
        progress_state={"last_report": 0},
        progress_lock=asyncio.Lock(),
    )

    assert "https://example.com" in crawler._scheduled
    assert crawler._url_queue.qsize() == 1


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_handles_httpx_429(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient([_make_response(429, "rate limited")])

    async def _fake_playwright(_url):
        return None, False, True

    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_playwright_first(
        "https://example.com", headers={}, include_rate_limit=True
    )

    assert result == (None, True)


@pytest.mark.asyncio
async def test_fetch_httpx_with_retries_connect_error(monkeypatch):
    request = httpx.Request("GET", "https://example.com")
    error = httpx.ConnectError("boom", request=request)
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient([error])
    crawler.config.max_retries = 1

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    content, _rate_limited = await crawler._fetch_httpx_with_retries(
        "https://example.com", headers={}
    )

    assert content is None
    assert _rate_limited is False


def test_supports_markdown_suffix_flag():
    config = CrawlConfig(markdown_url_suffix=".md")
    crawler = EfficientCrawler({"https://example.com"}, config)

    assert crawler._supports_markdown_suffix() is True


def test_create_client_uses_user_agent_provider():
    config = CrawlConfig(user_agent_provider=lambda: "TestAgent/1.0")
    crawler = EfficientCrawler({"https://example.com"}, config)

    client = crawler._create_client()
    try:
        assert client.headers["User-Agent"] == "TestAgent/1.0"
    finally:
        asyncio.run(client.aclose())


def test_get_cookie_file_path_defaults(tmp_path, monkeypatch):
    config = CrawlConfig(cookie_storage_dir=None)
    crawler = EfficientCrawler({"https://example.com"}, config)

    monkeypatch.setattr(
        "article_extractor.discovery.tempfile.gettempdir", lambda: str(tmp_path)
    )

    cookie_path = crawler._get_cookie_file_path()

    assert cookie_path.name.endswith(".json")
    assert cookie_path.parent.exists()


def test_load_cookies_handles_plain_values(tmp_path):
    config = CrawlConfig(cookie_storage_dir=tmp_path)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._cookies = httpx.Cookies()

    cookie_path = crawler._get_cookie_file_path()
    cookie_path.write_text('{"cookies": {"simple": "value"}}')

    asyncio.run(crawler._load_cookies())

    assert crawler._cookies.get("simple") == "value"


def test_rate_limit_state_multiplier_short_window(monkeypatch):
    state = HostRateLimitState(host="example.com", current_delay=2.0)
    state.last_429_time = 5.0
    state.consecutive_429s = 2

    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: 10.0)

    state.record_429()

    assert state.consecutive_429s == 3
    assert state.current_delay > 2.0


@pytest.mark.asyncio
async def test_rate_limiter_wait_sleeps(monkeypatch):
    limiter = AdaptiveRateLimiter(default_delay=1.0)

    times = iter([10.0, 10.5])
    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: next(times))

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)
    monkeypatch.setattr(limiter, "get_delay", lambda _url: 1.0)

    updated = await limiter.wait("https://example.com", last_request_time=9.8)

    assert updated == 10.5


@pytest.mark.asyncio
async def test_apply_rate_limit_with_url(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})

    async def _fake_wait(_url, _last):
        return 42.0

    monkeypatch.setattr(crawler._rate_limiter, "wait", _fake_wait)

    await crawler._apply_rate_limit("https://example.com")

    assert crawler._last_request_time == 42.0


@pytest.mark.asyncio
async def test_process_page_returns_failure_on_missing_content(monkeypatch):
    config = CrawlConfig(prefer_playwright=False)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.client = object()

    async def _noop_rate_limit(_url=None):
        return None

    async def _fake_fetch(_url, _headers, include_rate_limit=False):
        return None, True

    monkeypatch.setattr(crawler, "_apply_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(crawler, "_fetch_with_httpx_first", _fake_fetch)

    result = await crawler._process_page("https://example.com")

    assert result.success is False
    assert result.rate_limited is True


@pytest.mark.asyncio
async def test_handle_crawl_url_skips_when_visited(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._concurrency = AdaptiveConcurrencyLimiter(min_limit=1, max_limit=1)
    crawler.frontier.append("https://example.com")
    crawler._scheduled.add("https://example.com")
    crawler.visited.add("https://example.com")

    async def _noop_report(*_args, **_kwargs):
        return None

    monkeypatch.setattr(crawler, "_maybe_report_progress", _noop_report)

    await crawler._handle_crawl_url(
        "https://example.com",
        start_time=0.0,
        progress_state={"last_report": 0},
        progress_lock=asyncio.Lock(),
    )

    assert "https://example.com" not in crawler._scheduled


def test_should_skip_recent_respects_force_crawl():
    config = CrawlConfig(force_crawl=True, skip_recently_visited=lambda _url: True)
    crawler = EfficientCrawler({"https://example.com"}, config)

    assert crawler._should_skip_recent("https://example.com") is False


def test_convert_to_markdown_url_passthrough_cases():
    config = CrawlConfig(markdown_url_suffix=".md")
    crawler = EfficientCrawler({"https://example.com"}, config)

    assert (
        crawler._convert_to_markdown_url("https://example.com/", is_seed=False)
        == "https://example.com/"
    )
    assert (
        crawler._convert_to_markdown_url("https://example.com/doc.md", is_seed=False)
        == "https://example.com/doc.md"
    )


def test_normalize_url_keeps_querystrings():
    config = CrawlConfig(allow_querystrings=True)
    crawler = EfficientCrawler({"https://example.com"}, config)

    normalized = crawler._normalize_url("https://example.com/path?x=1")

    assert normalized == "https://example.com/path?x=1"


@pytest.mark.asyncio
async def test_fetch_with_httpx_first_falls_back_to_playwright(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = object()

    async def _fake_httpx(_url, _headers):
        return None, False

    async def _fake_playwright(_url):
        return "<html></html>", False, False

    monkeypatch.setattr(crawler, "_fetch_httpx_with_retries", _fake_httpx)
    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_httpx_first(
        "https://example.com", headers={}, include_rate_limit=False
    )

    assert result == "<html></html>"


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_handles_httpx_error(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient([_make_response(500, "boom")])

    async def _fake_playwright(_url):
        return None, False, True

    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_playwright_first(
        "https://example.com", headers={}, include_rate_limit=True
    )

    assert result == (None, False)


@pytest.mark.asyncio
async def test_fetch_playwright_handles_429(monkeypatch):
    from article_extractor import fetcher as fetcher_module

    class _Fetch429:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def fetch(self, _url):
            return "", 429

    crawler = EfficientCrawler({"https://example.com"})

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr(fetcher_module, "PlaywrightFetcher", _Fetch429)
    monkeypatch.setattr(crawler._rate_limiter, "get_delay", lambda _url: 0)
    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    content, _rate_limited, fallback = await crawler._fetch_playwright(
        "https://example.com"
    )

    assert content is None
    assert _rate_limited is True
    assert fallback is False


def test_rate_limit_state_recent_rate_no_events(monkeypatch):
    state = HostRateLimitState(host="example.com")
    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: 100.0)

    assert state.get_recent_429_rate() == 0.0


def test_rate_limit_state_get_delay(monkeypatch):
    state = HostRateLimitState(host="example.com", current_delay=2.0)

    class _FixedRandom:
        def uniform(self, _low, _high):
            return 1.0

    monkeypatch.setattr(secrets, "SystemRandom", lambda: _FixedRandom())

    assert state.get_delay() == 2.0


def test_adaptive_rate_limiter_get_delay(monkeypatch):
    limiter = AdaptiveRateLimiter(default_delay=2.0)

    class _FixedRandom:
        def uniform(self, _low, _high):
            return 1.0

    monkeypatch.setattr(secrets, "SystemRandom", lambda: _FixedRandom())

    assert limiter.get_delay("https://example.com") == 2.0


@pytest.mark.asyncio
async def test_rate_limiter_wait_no_sleep(monkeypatch):
    limiter = AdaptiveRateLimiter(default_delay=1.0)

    times = iter([10.0, 10.5])
    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: next(times))
    monkeypatch.setattr(limiter, "get_delay", lambda _url: 0.1)

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    updated = await limiter.wait("https://example.com", last_request_time=5.0)

    assert updated == 10.5


@pytest.mark.asyncio
async def test_context_exit_with_no_client():
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = None
    crawler._cookies = None

    await crawler.__aexit__(None, None, None)


def test_load_cookies_no_cookie_store():
    crawler = EfficientCrawler({"https://example.com"})
    crawler._cookies = None

    asyncio.run(crawler._load_cookies())


def test_save_cookies_no_cookie_store():
    crawler = EfficientCrawler({"https://example.com"})
    crawler._cookies = None

    asyncio.run(crawler._save_cookies())


def test_create_client_uses_default_user_agent():
    crawler = EfficientCrawler({"https://example.com"})

    client = crawler._create_client()
    try:
        assert "Mozilla" in client.headers["User-Agent"]
    finally:
        asyncio.run(client.aclose())


def test_report_progress_with_queue():
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._url_queue.put_nowait("https://example.com")
    crawler.collected.add("https://example.com")

    crawler._report_progress(start_time=0.0)


def test_report_progress_without_queue():
    crawler = EfficientCrawler({"https://example.com"})
    crawler.frontier.append("https://example.com")
    crawler.collected.add("https://example.com")

    crawler._report_progress(start_time=0.0)


def test_log_completion_with_rate_limit_stats():
    crawler = EfficientCrawler({"https://example.com"})
    crawler.collected.add("https://example.com")
    crawler._crawler_skipped = 1
    crawler._rate_limiter.record_429("https://example.com")

    crawler._log_completion(start_time=0.0)


def test_log_completion_without_rate_limit_stats(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.collected.add("https://example.com")
    monkeypatch.setattr(
        crawler._rate_limiter,
        "get_stats",
        lambda: {
            "example.com": {
                "total_429s": 0,
                "total_requests": 2,
                "current_delay": 0.0,
            }
        },
    )

    crawler._log_completion(start_time=0.0)


@pytest.mark.asyncio
async def test_handle_crawl_url_stops_when_flag_set(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._concurrency = AdaptiveConcurrencyLimiter(min_limit=1, max_limit=1)
    crawler.frontier.append("https://example.com")
    crawler._scheduled.add("https://example.com")
    crawler._stop_crawl = True

    await crawler._handle_crawl_url(
        "https://example.com",
        start_time=0.0,
        progress_state={"last_report": 0},
        progress_lock=asyncio.Lock(),
    )

    assert "https://example.com" not in crawler._scheduled


@pytest.mark.asyncio
async def test_handle_crawl_url_records_exception(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._concurrency = AdaptiveConcurrencyLimiter(min_limit=1, max_limit=1)
    crawler.frontier.append("https://example.com")
    crawler._scheduled.add("https://example.com")

    async def _boom(_url):
        raise RuntimeError("boom")

    async def _noop_report(*_args, **_kwargs):
        return None

    monkeypatch.setattr(crawler, "_process_page", _boom)
    monkeypatch.setattr(crawler, "_maybe_report_progress", _noop_report)

    await crawler._handle_crawl_url(
        "https://example.com",
        start_time=0.0,
        progress_state={"last_report": 0},
        progress_lock=asyncio.Lock(),
    )


def test_coerce_fetch_result_passthrough():
    crawler = EfficientCrawler({"https://example.com"})

    assert crawler._coerce_fetch_result("ok") == ("ok", False)


@pytest.mark.asyncio
async def test_process_page_uses_referer_and_filters_links(monkeypatch):
    config = CrawlConfig(
        prefer_playwright=True, should_process_url=lambda url: "keep" in url
    )
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.client = object()
    crawler._normalized_seed_urls = {"https://example.com"}
    crawler._url_queue = asyncio.Queue()
    crawler._last_url = "https://example.com/prev"

    async def _noop_rate_limit(_url=None):
        return None

    async def _fake_fetch(_url, headers, include_rate_limit=False):
        assert headers.get("Referer") == "https://example.com/prev"
        return (
            "<html><a href='mailto:test@example.com'></a><a href='https://example.com/keep'></a></html>",
            False,
        )

    monkeypatch.setattr(crawler, "_apply_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(crawler, "_fetch_with_playwright_first", _fake_fetch)

    result = await crawler._process_page("https://example.com")

    assert result.success is True
    assert crawler._url_queue.qsize() == 1


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_no_fallback(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = object()

    async def _fake_playwright(_url):
        return "ok", False, False

    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_playwright_first(
        "https://example.com", headers={}, include_rate_limit=False
    )

    assert result == "ok"


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_handles_httpx_429_exception(monkeypatch):
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("boom", request=request, response=response)
    crawler = EfficientCrawler({"https://example.com"})

    class _FailingClient:
        async def get(self, _url, headers=None):
            raise error

    crawler.client = _FailingClient()

    async def _fake_playwright(_url):
        return None, False, True

    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_playwright_first(
        "https://example.com", headers={}, include_rate_limit=True
    )

    assert result == (None, True)


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_handles_httpx_exception(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})

    class _FailingClient:
        async def get(self, _url, headers=None):
            raise RuntimeError("boom")

    crawler.client = _FailingClient()

    async def _fake_playwright(_url):
        return None, False, True

    monkeypatch.setattr(crawler, "_fetch_playwright", _fake_playwright)

    result = await crawler._fetch_with_playwright_first(
        "https://example.com", headers={}, include_rate_limit=True
    )

    assert result == (None, False)


@pytest.mark.asyncio
async def test_fetch_playwright_success(monkeypatch):
    from article_extractor import fetcher as fetcher_module

    class _FetchOk:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def fetch(self, _url):
            return "<html></html>", 200

    crawler = EfficientCrawler({"https://example.com"})

    monkeypatch.setattr(fetcher_module, "PlaywrightFetcher", _FetchOk)

    content, _rate_limited, fallback = await crawler._fetch_playwright(
        "https://example.com"
    )

    assert content == "<html></html>"
    assert _rate_limited is False
    assert fallback is False


@pytest.mark.asyncio
async def test_fetch_playwright_handles_non_fd_oserror(monkeypatch):
    from article_extractor import fetcher as fetcher_module

    class _FailingFetcher:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            raise OSError(1, "oops")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    crawler = EfficientCrawler({"https://example.com"})

    monkeypatch.setattr(fetcher_module, "PlaywrightFetcher", _FailingFetcher)

    content, _rate_limited, fallback = await crawler._fetch_playwright(
        "https://example.com"
    )

    assert content is None
    assert fallback is True


@pytest.mark.asyncio
async def test_fetch_httpx_with_retries_http_status_errors(monkeypatch):
    request = httpx.Request("GET", "https://example.com")
    response_429 = httpx.Response(429, request=request)
    response_418 = httpx.Response(418, request=request)
    error_429 = httpx.HTTPStatusError("boom", request=request, response=response_429)
    error_418 = httpx.HTTPStatusError("nope", request=request, response=response_418)

    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient([error_429, error_418])
    crawler.config.max_retries = 2

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)
    monkeypatch.setattr(crawler._rate_limiter, "get_delay", lambda _url: 0)

    content, rate_limited = await crawler._fetch_httpx_with_retries(
        "https://example.com", headers={}
    )

    assert content is None
    assert rate_limited is True


@pytest.mark.asyncio
async def test_fetch_httpx_with_retries_generic_exception(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler.client = _SequenceClient([RuntimeError("boom")])
    crawler.config.max_retries = 1

    async def _noop_sleep(_delay):
        return None

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _noop_sleep)

    content, rate_limited = await crawler._fetch_httpx_with_retries(
        "https://example.com", headers={}
    )

    assert content is None
    assert rate_limited is False


def test_extract_links_handles_list_href(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})

    class _Node:
        attrs = {"href": ["/docs"]}

    class _Doc:
        root = _Node()

    monkeypatch.setattr("article_extractor.discovery.JustHTML", lambda _html: _Doc())
    monkeypatch.setattr(crawler, "_iter_nodes", lambda _node: [_Node()])

    links = crawler._extract_links("<html></html>", "https://example.com")

    assert "https://example.com/docs" in links


def test_convert_to_markdown_url_handles_exception(monkeypatch):
    crawler = EfficientCrawler(
        {"https://example.com"}, CrawlConfig(markdown_url_suffix=".md")
    )

    monkeypatch.setattr(
        "article_extractor.discovery.urlparse",
        lambda _url: (_ for _ in ()).throw(ValueError("boom")),
    )

    assert (
        crawler._convert_to_markdown_url("https://example.com/docs", is_seed=False)
        == "https://example.com/docs"
    )


def test_normalize_url_handles_exception(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})

    monkeypatch.setattr(
        "article_extractor.discovery.urldefrag",
        lambda _url: (_ for _ in ()).throw(ValueError("boom")),
    )

    assert crawler._normalize_url("https://example.com") is None


def test_rate_limit_state_multiplier_medium_window(monkeypatch):
    state = HostRateLimitState(host="example.com", current_delay=2.0)
    state.last_429_time = 60.0

    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: 100.0)

    state.record_429()

    assert state.current_delay > 2.0


def test_load_cookies_handles_invalid_json(tmp_path):
    config = CrawlConfig(cookie_storage_dir=tmp_path)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._cookies = httpx.Cookies()

    cookie_path = crawler._get_cookie_file_path()
    cookie_path.write_text("not-json")

    asyncio.run(crawler._load_cookies())


def test_save_cookies_handles_write_error(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._cookies = httpx.Cookies()
    crawler._cookies.set("session", "value")

    class _BadPath:
        def write_text(self, _value):
            raise OSError("boom")

    monkeypatch.setattr(crawler, "_get_cookie_file_path", lambda: _BadPath())

    asyncio.run(crawler._save_cookies())


def test_initialize_frontier_dedupes_normalized_urls():
    crawler = EfficientCrawler({"https://example.com", "https://example.com#frag"})

    seeds = crawler._initialize_frontier()

    assert seeds == ["https://example.com/"]


def test_remove_from_frontier_noop_when_empty():
    crawler = EfficientCrawler({"https://example.com"})

    crawler._remove_from_frontier("https://example.com")


@pytest.mark.asyncio
async def test_process_page_filters_links_by_should_process(monkeypatch):
    config = CrawlConfig(
        prefer_playwright=False, should_process_url=lambda url: "allow" in url
    )
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.client = object()
    crawler._url_queue = asyncio.Queue()

    async def _noop_rate_limit(_url=None):
        return None

    async def _fake_fetch(_url, _headers, include_rate_limit=False):
        return (
            "<html><a href='https://example.com/deny'></a></html>",
            False,
        )

    monkeypatch.setattr(crawler, "_apply_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(crawler, "_fetch_with_httpx_first", _fake_fetch)

    result = await crawler._process_page("https://example.com")

    assert result.success is True
    assert crawler._url_queue.qsize() == 0


@pytest.mark.asyncio
async def test_fetch_playwright_handles_generic_exception(monkeypatch):
    from article_extractor import fetcher as fetcher_module

    class _FailingFetcher:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            raise RuntimeError("boom")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    crawler = EfficientCrawler({"https://example.com"})

    monkeypatch.setattr(fetcher_module, "PlaywrightFetcher", _FailingFetcher)

    content, _rate_limited, fallback = await crawler._fetch_playwright(
        "https://example.com"
    )

    assert content is None
    assert fallback is True


def test_create_client_requires_httpx(monkeypatch):
    import builtins

    crawler = EfficientCrawler({"https://example.com"})

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)

    with pytest.raises(ImportError, match="httpx not installed"):
        crawler._create_client()


@pytest.mark.asyncio
async def test_crawl_requires_context_manager():
    crawler = EfficientCrawler({"https://example.com"})

    with pytest.raises(RuntimeError, match="async context manager"):
        await crawler.crawl()


@pytest.mark.asyncio
async def test_crawl_worker_requires_queue():
    crawler = EfficientCrawler({"https://example.com"})

    with pytest.raises(RuntimeError, match="queue not initialized"):
        await crawler._crawl_worker(0.0, {"last_report": 0}, asyncio.Lock())


@pytest.mark.asyncio
async def test_process_page_requires_client():
    crawler = EfficientCrawler({"https://example.com"})

    with pytest.raises(RuntimeError, match="async context manager"):
        await crawler._process_page("https://example.com")


@pytest.mark.asyncio
async def test_fetch_with_playwright_first_requires_client():
    crawler = EfficientCrawler({"https://example.com"})

    with pytest.raises(RuntimeError, match="Client must be initialized"):
        await crawler._fetch_with_playwright_first("https://example.com", {})


@pytest.mark.asyncio
async def test_fetch_with_httpx_first_requires_client():
    crawler = EfficientCrawler({"https://example.com"})

    with pytest.raises(RuntimeError, match="Client must be initialized"):
        await crawler._fetch_with_httpx_first("https://example.com", {})


@pytest.mark.asyncio
async def test_handle_crawl_url_records_success(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._concurrency = AdaptiveConcurrencyLimiter(1, 1)

    async def _fake_acquire():
        return None

    async def _fake_release():
        return None

    crawler._concurrency.acquire = _fake_acquire  # type: ignore[assignment]
    crawler._concurrency.release = _fake_release  # type: ignore[assignment]
    crawler._concurrency.record_success = AsyncMock()
    crawler._concurrency.record_rate_limit = AsyncMock()

    monkeypatch.setattr(
        crawler, "_process_page", AsyncMock(return_value=PageProcessResult(True))
    )
    monkeypatch.setattr(crawler, "_maybe_report_progress", AsyncMock())

    await crawler._handle_crawl_url("https://example.com", 0.0, {}, asyncio.Lock())

    crawler._concurrency.record_success.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_crawl_url_records_failure(monkeypatch):
    crawler = EfficientCrawler({"https://example.com"})
    crawler._url_queue = asyncio.Queue()
    crawler._concurrency = AdaptiveConcurrencyLimiter(1, 1)

    async def _fake_acquire():
        return None

    async def _fake_release():
        return None

    crawler._concurrency.acquire = _fake_acquire  # type: ignore[assignment]
    crawler._concurrency.release = _fake_release  # type: ignore[assignment]
    crawler._concurrency.record_success = AsyncMock()
    crawler._concurrency.record_rate_limit = AsyncMock()

    monkeypatch.setattr(
        crawler,
        "_process_page",
        AsyncMock(return_value=PageProcessResult(success=False, rate_limited=False)),
    )
    monkeypatch.setattr(crawler, "_maybe_report_progress", AsyncMock())

    await crawler._handle_crawl_url("https://example.com", 0.0, {}, asyncio.Lock())

    crawler._concurrency.record_success.assert_not_awaited()
    crawler._concurrency.record_rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_page_queues_links(monkeypatch):
    config = CrawlConfig(prefer_playwright=False)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.client = object()
    crawler._url_queue = asyncio.Queue()

    async def _noop_rate_limit(_url=None):
        return None

    async def _fake_fetch(_url, _headers, include_rate_limit=False):
        return "<html><a href='https://example.com/docs'></a></html>", False

    monkeypatch.setattr(crawler, "_apply_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(crawler, "_fetch_with_httpx_first", _fake_fetch)
    monkeypatch.setattr(
        crawler, "_extract_links", lambda *_a, **_k: {"https://example.com/docs"}
    )

    result = await crawler._process_page("https://example.com")

    assert result.success is True
    assert crawler._url_queue.qsize() == 1


@pytest.mark.asyncio
async def test_process_page_without_queue_still_discovers_links(monkeypatch):
    config = CrawlConfig(prefer_playwright=False)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler.client = object()

    async def _noop_rate_limit(_url=None):
        return None

    async def _fake_fetch(_url, _headers, include_rate_limit=False):
        return "<html><a href='https://example.com/docs'></a></html>", False

    monkeypatch.setattr(crawler, "_apply_rate_limit", _noop_rate_limit)
    monkeypatch.setattr(crawler, "_fetch_with_httpx_first", _fake_fetch)
    monkeypatch.setattr(
        crawler, "_extract_links", lambda *_a, **_k: {"https://example.com/docs"}
    )

    result = await crawler._process_page("https://example.com")

    assert result.success is True
    assert crawler.frontier


@pytest.mark.asyncio
async def test_apply_rate_limit_without_url_sleeps(monkeypatch):
    config = CrawlConfig(delay_seconds=0.5)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._last_request_time = 9.9

    times = iter([10.0, 10.5])
    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: next(times))

    sleep_calls = []

    async def _fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", _fake_sleep)

    await crawler._apply_rate_limit()

    assert sleep_calls


@pytest.mark.asyncio
async def test_apply_rate_limit_without_url_no_sleep_when_elapsed(monkeypatch):
    config = CrawlConfig(delay_seconds=0.5)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._last_request_time = 1.0

    times = iter([2.0, 2.1])
    monkeypatch.setattr("article_extractor.discovery.time.time", lambda: next(times))
    sleep_mock = AsyncMock()
    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", sleep_mock)

    await crawler._apply_rate_limit()

    sleep_mock.assert_not_awaited()
    assert crawler._last_request_time == 2.1


@pytest.mark.asyncio
async def test_apply_rate_limit_without_delay_returns(monkeypatch):
    config = CrawlConfig(delay_seconds=0.0)
    crawler = EfficientCrawler({"https://example.com"}, config)
    crawler._last_request_time = 5.0

    sleep_mock = AsyncMock()
    monkeypatch.setattr("article_extractor.discovery.asyncio.sleep", sleep_mock)

    await crawler._apply_rate_limit()

    sleep_mock.assert_not_awaited()
    assert crawler._last_request_time == 5.0
