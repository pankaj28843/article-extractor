import httpx
import pytest

from article_extractor.discovery import (
    AdaptiveConcurrencyLimiter,
    CrawlConfig,
    EfficientCrawler,
    HostRateLimitState,
    PageProcessResult,
)


class _FakeClient:
    def __init__(self):
        self.cookies = httpx.Cookies()

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_crawler_skips_recently_visited_urls(monkeypatch, tmp_path):
    skip_url = "https://example.com/skip"
    keep_url = "https://example.com/keep"

    def _skip_recent(url: str) -> bool:
        return url == skip_url

    config = CrawlConfig(
        max_pages=2,
        skip_recently_visited=_skip_recent,
        prefer_playwright=False,
        cookie_storage_dir=tmp_path,
    )
    crawler = EfficientCrawler({skip_url, keep_url}, config)

    monkeypatch.setattr(crawler, "_create_client", lambda: _FakeClient())

    async def _fake_process(url: str):
        crawler.collected.add(url)
        return PageProcessResult(success=True)

    monkeypatch.setattr(crawler, "_process_page", _fake_process)

    async with crawler:
        await crawler.crawl()

    assert crawler._crawler_skipped == 1
    assert skip_url in crawler.visited


def test_extract_links_with_href_attributes():
    crawler = EfficientCrawler({"https://example.com/"})
    html = """
    <html>
        <body>
            <a href="/docs/page1">Page 1</a>
            <div href="/docs/page2">Page 2</div>
        </body>
    </html>
    """

    links = crawler._extract_links(html, "https://example.com/")

    assert "https://example.com/docs/page1" in links
    assert "https://example.com/docs/page2" in links


def test_rate_limit_state_reduces_delay_after_success_streak():
    state = HostRateLimitState(host="example.com", base_delay=2.0, current_delay=2.0)
    for _ in range(10):
        state.record_success()
    assert state.current_delay < 2.0


@pytest.mark.asyncio
async def test_concurrency_limiter_grows_after_successes():
    limiter = AdaptiveConcurrencyLimiter(min_limit=1, max_limit=2)
    for _ in range(25):
        await limiter.record_success()
    assert limiter.snapshot()["current_limit"] == 2
