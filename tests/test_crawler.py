from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from article_extractor.crawler import (
    Crawler,
    CrawlProgress,
    check_disk_space,
    extract_links,
    is_sitemap_index,
    load_manifest,
    load_sitemap,
    parse_sitemap_xml,
    run_crawl,
    validate_output_dir,
    write_manifest,
)
from article_extractor.types import (
    CrawlConfig,
    CrawlManifest,
    CrawlResult,
    NetworkOptions,
)


@pytest.mark.asyncio
async def test_crawler_enqueues_seed_urls_with_max_pages(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/first", "https://example.com/second"],
        max_pages=1,
    )
    crawler = Crawler(config)

    first = await crawler.get_next_target()
    assert first is not None
    assert first.url == "https://example.com/first"
    crawler.task_done()

    # No additional URLs should be available once max_pages is reached.
    crawler.close()
    assert await crawler.get_next_target() is None


@pytest.mark.asyncio
async def test_crawler_allow_and_deny_filters(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        allow_prefixes=["https://example.com/articles"],
        deny_prefixes=["https://example.com/articles/drafts"],
        max_pages=5,
    )
    crawler = Crawler(config)

    assert crawler.enqueue_url("https://example.com/articles/1", depth=0)
    assert not crawler.enqueue_url("https://example.com/blog/1", depth=0)
    assert not crawler.enqueue_url(
        "https://example.com/articles/drafts/secret", depth=0
    )

    target = await crawler.get_next_target()
    assert target is not None
    assert target.url == "https://example.com/articles/1"
    crawler.task_done()
    crawler.close()
    assert await crawler.get_next_target() is None


@pytest.mark.asyncio
async def test_crawler_rate_limit_serializes_same_host(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        rate_limit_delay=0.2,
        concurrency=2,
    )
    crawler = Crawler(config)

    timestamps: list[float] = []
    loop = asyncio.get_running_loop()

    async def worker() -> None:
        async with crawler.acquire_slot("https://example.com/path"):
            timestamps.append(loop.time())

    await asyncio.gather(worker(), worker())

    assert len(timestamps) == 2
    timestamps.sort()
    assert timestamps[1] - timestamps[0] >= 0.18


@pytest.mark.asyncio
async def test_crawler_iter_targets_consumes_until_close(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/a", "https://example.com/b"],
    )
    crawler = Crawler(config)

    collected: list[str] = []

    async def consume() -> None:
        async for target in crawler.iter_targets():
            collected.append(target.url)
            crawler.task_done()

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    crawler.close()
    await consumer

    assert collected == ["https://example.com/a", "https://example.com/b"]


def test_crawler_close_is_idempotent(tmp_path: Path) -> None:
    crawler = Crawler(CrawlConfig(output_dir=tmp_path))

    crawler.close()
    crawler.close()  # Should not raise


def test_crawler_tracks_capacity_and_rejects_invalid_urls(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path, max_pages=2)
    crawler = Crawler(config)

    assert crawler.has_capacity()
    assert crawler.enqueue_url("https://example.com/one", depth=0)
    assert crawler.enqueue_url("https://example.com/two", depth=1)
    assert not crawler.has_capacity()
    assert crawler.queue_size() == 2
    assert crawler.total_enqueued() == 2
    assert len(crawler.visited_urls()) == 2
    assert not crawler.enqueue_url("invalid url", depth=0)
    assert not crawler.enqueue_url("/relative", depth=0)


def test_crawler_respects_depth_and_duplicate_rules(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path, max_depth=1, max_pages=3)
    crawler = Crawler(config)

    assert crawler.enqueue_url("https://example.com/one", depth=1)
    assert not crawler.enqueue_url("https://example.com/two", depth=2)
    assert not crawler.enqueue_url("https://example.com/one", depth=1)


@pytest.mark.asyncio
async def test_crawler_accepts_urls_without_scheme(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path, max_pages=3)
    crawler = Crawler(config)

    assert crawler.enqueue_url("example.com/path", depth=0)
    target = await crawler.get_next_target()
    assert target is not None
    assert target.url == "http://example.com/path"
    crawler.task_done()
    crawler.close()
    assert await crawler.get_next_target() is None


def test_crawler_prefix_normalization_handles_invalid_values(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        allow_prefixes=["", "/relative"],
        deny_prefixes=["//", "bad"],
        max_pages=1,
    )
    crawler = Crawler(config)

    assert crawler.enqueue_url("https://example.com/doc", depth=0)


@pytest.mark.asyncio
async def test_crawler_acquire_slot_handles_missing_host(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    async with crawler.acquire_slot("not-a-valid-url"):
        assert crawler._host_key("not-a-valid-url") is None
        assert crawler._host_key("http://[::1") is None


@pytest.mark.asyncio
async def test_crawler_open_fetcher_uses_default_selector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    created_networks: list[NetworkOptions | None] = []

    class StubFetcher:
        def __init__(self, *, network: NetworkOptions | None = None) -> None:
            self.network = network
            created_networks.append(network)

        async def __aenter__(self) -> StubFetcher:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def fetch(self, url: str) -> tuple[str, int]:
            return "<html />", 200

    def fake_get_default_fetcher(prefer_playwright: bool) -> type[StubFetcher]:
        assert prefer_playwright is False
        return StubFetcher

    sentinel_network = NetworkOptions(headed=True)

    monkeypatch.setattr(
        "article_extractor.crawler.get_default_fetcher",
        fake_get_default_fetcher,
    )
    monkeypatch.setattr(
        "article_extractor.crawler.resolve_network_options",
        lambda: sentinel_network,
    )

    async with crawler.open_fetcher(prefer_playwright=False) as fetcher:
        assert isinstance(fetcher, StubFetcher)
        assert fetcher.network is sentinel_network

    assert created_networks == [sentinel_network]


@pytest.mark.asyncio
async def test_crawler_fetch_with_retry_retries_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = CrawlConfig(output_dir=tmp_path, rate_limit_delay=0)
    crawler = Crawler(config)

    class FlakyFetcher:
        def __init__(self) -> None:
            self.calls = 0

        async def fetch(self, url: str) -> tuple[str, int]:
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("boom")
            return "content", 200

    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("article_extractor.crawler.asyncio.sleep", fake_sleep)

    fetcher = FlakyFetcher()
    html, status = await crawler.fetch_with_retry(
        "https://example.com/page",
        fetcher,
        max_attempts=3,
    )

    assert html == "content"
    assert status == 200
    assert fetcher.calls == 3
    assert sleep_calls == [0.3, 0.6]


@pytest.mark.asyncio
async def test_crawler_fetch_with_retry_raises_after_exhaustion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = CrawlConfig(output_dir=tmp_path, rate_limit_delay=0)
    crawler = Crawler(config)

    class AlwaysFailFetcher:
        async def fetch(self, url: str) -> tuple[str, int]:
            raise RuntimeError("nope")

    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("article_extractor.crawler.asyncio.sleep", fake_sleep)

    with pytest.raises(RuntimeError):
        await crawler.fetch_with_retry(
            "https://example.com",
            AlwaysFailFetcher(),
            max_attempts=2,
        )

    assert sleep_calls == [0.3]


# ----------------------------------------------------------------------
# Sitemap parsing tests
# ----------------------------------------------------------------------

SAMPLE_URLSET = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>
"""

SAMPLE_SITEMAPINDEX = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap2.xml</loc></sitemap>
</sitemapindex>
"""

SAMPLE_URLSET_NO_NS = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://example.com/no-ns</loc></url>
</urlset>
"""


def test_parse_sitemap_xml_extracts_urls_from_urlset() -> None:
    urls = parse_sitemap_xml(SAMPLE_URLSET)
    assert urls == ["https://example.com/page1", "https://example.com/page2"]


def test_parse_sitemap_xml_extracts_urls_from_sitemapindex() -> None:
    urls = parse_sitemap_xml(SAMPLE_SITEMAPINDEX)
    assert urls == [
        "https://example.com/sitemap1.xml",
        "https://example.com/sitemap2.xml",
    ]


def test_parse_sitemap_xml_handles_no_namespace() -> None:
    urls = parse_sitemap_xml(SAMPLE_URLSET_NO_NS)
    assert urls == ["https://example.com/no-ns"]


def test_parse_sitemap_xml_handles_malformed_xml() -> None:
    urls = parse_sitemap_xml("<not valid xml")
    assert urls == []


def test_is_sitemap_index_detects_index() -> None:
    assert is_sitemap_index(SAMPLE_SITEMAPINDEX) is True
    assert is_sitemap_index(SAMPLE_URLSET) is False
    assert is_sitemap_index("<broken") is False


@pytest.mark.asyncio
async def test_load_sitemap_reads_local_file(tmp_path: Path) -> None:
    sitemap_file = tmp_path / "sitemap.xml"
    sitemap_file.write_text(SAMPLE_URLSET, encoding="utf-8")

    urls = await load_sitemap(str(sitemap_file))
    assert urls == ["https://example.com/page1", "https://example.com/page2"]


@pytest.mark.asyncio
async def test_load_sitemap_handles_missing_file() -> None:
    urls = await load_sitemap("/nonexistent/sitemap.xml")
    assert urls == []


@pytest.mark.asyncio
async def test_load_sitemap_fetches_remote_url() -> None:
    class StubFetcher:
        async def fetch(self, url: str) -> tuple[str, int]:
            return SAMPLE_URLSET, 200

    urls = await load_sitemap("https://example.com/sitemap.xml", StubFetcher())
    assert urls == ["https://example.com/page1", "https://example.com/page2"]


@pytest.mark.asyncio
async def test_load_sitemap_recurses_sitemapindex() -> None:
    responses = {
        "https://example.com/sitemap.xml": SAMPLE_SITEMAPINDEX,
        "https://example.com/sitemap1.xml": SAMPLE_URLSET,
        "https://example.com/sitemap2.xml": SAMPLE_URLSET_NO_NS,
    }

    class StubFetcher:
        async def fetch(self, url: str) -> tuple[str, int]:
            return responses.get(url, ""), 200

    urls = await load_sitemap("https://example.com/sitemap.xml", StubFetcher())
    assert set(urls) == {
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/no-ns",
    }


@pytest.mark.asyncio
async def test_load_sitemap_no_fetcher_for_remote() -> None:
    urls = await load_sitemap("https://example.com/sitemap.xml", None)
    assert urls == []


@pytest.mark.asyncio
async def test_load_sitemap_handles_fetch_error() -> None:
    class FailingFetcher:
        async def fetch(self, url: str) -> tuple[str, int]:
            raise RuntimeError("network error")

    urls = await load_sitemap("https://example.com/sitemap.xml", FailingFetcher())
    assert urls == []


@pytest.mark.asyncio
async def test_load_sitemap_handles_bad_status() -> None:
    class BadStatusFetcher:
        async def fetch(self, url: str) -> tuple[str, int]:
            return "", 404

    urls = await load_sitemap("https://example.com/sitemap.xml", BadStatusFetcher())
    assert urls == []


# ----------------------------------------------------------------------
# Link discovery tests
# ----------------------------------------------------------------------


def test_extract_links_finds_absolute_urls() -> None:
    html = """
    <html>
    <body>
        <a href="https://example.com/page1">Link 1</a>
        <a href="https://other.com/page2">Link 2</a>
    </body>
    </html>
    """
    links = extract_links(html, "https://example.com/")
    assert links == ["https://example.com/page1", "https://other.com/page2"]


def test_extract_links_resolves_relative_urls() -> None:
    html = """
    <a href="/about">About</a>
    <a href="contact.html">Contact</a>
    <a href="../parent">Parent</a>
    """
    links = extract_links(html, "https://example.com/docs/page.html")
    assert links == [
        "https://example.com/about",
        "https://example.com/docs/contact.html",
        "https://example.com/parent",
    ]


def test_extract_links_skips_non_http_schemes() -> None:
    html = """
    <a href="mailto:test@example.com">Email</a>
    <a href="javascript:void(0)">JS</a>
    <a href="ftp://files.example.com">FTP</a>
    <a href="https://example.com/valid">Valid</a>
    """
    links = extract_links(html, "https://example.com/")
    assert links == ["https://example.com/valid"]


def test_extract_links_handles_empty_href() -> None:
    html = '<a href="">Empty</a><a>No href</a>'
    links = extract_links(html, "https://example.com/")
    assert links == []


def test_extract_links_handles_malformed_html() -> None:
    html = "<a href='https://example.com/page'>Link<"
    links = extract_links(html, "https://example.com/")
    assert links == ["https://example.com/page"]


def test_crawler_discover_links_enqueues_valid_links(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        allow_prefixes=["https://example.com/"],
        max_pages=10,
        follow_links=True,
    )
    crawler = Crawler(config)

    html = """
    <a href="https://example.com/page1">Page 1</a>
    <a href="https://example.com/page2">Page 2</a>
    <a href="https://other.com/page3">Other</a>
    """
    enqueued = crawler.discover_links(html, "https://example.com/", parent_depth=0)

    assert enqueued == 2
    assert crawler.total_enqueued() == 2


def test_crawler_discover_links_respects_follow_links_false(tmp_path: Path) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        max_pages=10,
        follow_links=False,
    )
    crawler = Crawler(config)

    html = '<a href="https://example.com/page1">Page 1</a>'
    enqueued = crawler.discover_links(html, "https://example.com/", parent_depth=0)

    assert enqueued == 0
    assert crawler.total_enqueued() == 0


@pytest.mark.asyncio
async def test_crawler_load_sitemaps_enqueues_urls(tmp_path: Path) -> None:
    sitemap_file = tmp_path / "sitemap.xml"
    sitemap_file.write_text(SAMPLE_URLSET, encoding="utf-8")

    config = CrawlConfig(
        output_dir=tmp_path,
        sitemaps=[str(sitemap_file)],
        max_pages=10,
    )
    crawler = Crawler(config)

    enqueued = await crawler.load_sitemaps()
    assert enqueued == 2


# ----------------------------------------------------------------------
# Extraction pipeline tests (Phase 2.1)
# ----------------------------------------------------------------------

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
<article>
<h1>Test Article Title</h1>
<p>This is a test article with enough content to pass extraction thresholds.
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis
nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore
eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident,
sunt in culpa qui officia deserunt mollit anim id est laborum.</p>
<p>Second paragraph with more content to ensure word count threshold is met.
This ensures the extraction succeeds with meaningful content.</p>
</article>
</body>
</html>
"""


def test_crawler_extract_page_success(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    result = crawler.extract_page(SAMPLE_HTML, "https://example.com/article")

    assert result.status == "success"
    assert result.url == "https://example.com/article"
    assert result.word_count > 0
    assert result.title != ""
    assert result.extracted_at != ""
    assert result.error is None


def test_crawler_extract_page_empty_html_returns_zero_words(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    result = crawler.extract_page("", "https://example.com/empty")

    # Extractor succeeds but with zero word count for empty content
    assert result.status == "success"
    assert result.word_count == 0


def test_crawler_extract_page_minimal_html_returns_zero_words(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    result = crawler.extract_page(
        "<html><body><nav>Menu</nav></body></html>",
        "https://example.com/no-content",
    )

    # Extractor succeeds but with minimal/zero word count
    assert result.status == "success"
    assert result.word_count == 0


# ----------------------------------------------------------------------
# Markdown writer tests (Phase 2.2)
# ----------------------------------------------------------------------


def test_crawler_write_markdown_creates_file(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    file_path = crawler.write_markdown(
        url="https://example.com/article/test",
        title="Test Title",
        markdown="# Test\n\nContent here.",
        word_count=5,
        extracted_at="2026-01-05T00:00:00Z",
    )

    assert file_path.exists()
    assert file_path.suffix == ".md"
    assert "example.com" in str(file_path)

    content = file_path.read_text()
    assert "url: https://example.com/article/test" in content
    assert 'title: "Test Title"' in content
    assert "word_count: 5" in content
    assert "# Test\n\nContent here." in content


def test_crawler_write_markdown_escapes_title_quotes(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    file_path = crawler.write_markdown(
        url="https://example.com/page",
        title='Title with "quotes"',
        markdown="Content",
        word_count=1,
        extracted_at="2026-01-05T00:00:00Z",
    )

    content = file_path.read_text()
    assert r'title: "Title with \"quotes\""' in content


def test_crawler_url_to_filepath_deterministic(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    path1 = crawler._url_to_filepath("https://example.com/blog/post-1")
    path2 = crawler._url_to_filepath("https://example.com/blog/post-1")
    path3 = crawler._url_to_filepath("https://example.com/blog/post-2")

    assert path1 == path2
    assert path1 != path3
    assert path1.suffix == ".md"
    # Verify flat structure: file directly in output_dir, no nested dirs
    assert path1.parent == tmp_path
    # Verify __ separator between hostname and path components
    assert path1.name == "example.com__blog__post-1.md"


def test_crawler_url_to_filepath_handles_query_strings(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    path = crawler._url_to_filepath("https://example.com/search?q=test&page=1")

    assert path.suffix == ".md"
    # Verify flat structure
    assert path.parent == tmp_path
    # Query string is appended and sanitized
    assert "search" in path.name
    assert "q_test" in path.name or "page_1" in path.name


def test_crawler_url_to_filepath_handles_root_url(tmp_path: Path) -> None:
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    path = crawler._url_to_filepath("https://example.com/")

    assert path.suffix == ".md"
    # Verify flat structure
    assert path.parent == tmp_path
    # Root URL becomes hostname__index.md
    assert path.name == "example.com__index.md"


def test_crawler_url_to_filepath_flattens_deep_paths(tmp_path: Path) -> None:
    """Verify deeply nested paths are flattened with __ separators."""
    config = CrawlConfig(output_dir=tmp_path)
    crawler = Crawler(config)

    path = crawler._url_to_filepath(
        "https://wiki.example.com/spaces/DOCS/pages/12345678/GettingStarted"
    )

    assert path.suffix == ".md"
    # Verify flat structure: no nested directories
    assert path.parent == tmp_path
    # All path separators replaced with __
    expected_name = "wiki.example.com__spaces__DOCS__pages__12345678__GettingStarted.md"
    assert path.name == expected_name


# ----------------------------------------------------------------------
# Output directory validation tests (Phase 2.4)
# ----------------------------------------------------------------------


def test_validate_output_dir_creates_missing(tmp_path: Path) -> None:
    new_dir = tmp_path / "new_output"
    validate_output_dir(new_dir, create=True)
    assert new_dir.exists()
    assert new_dir.is_dir()


def test_validate_output_dir_accepts_existing(tmp_path: Path) -> None:
    validate_output_dir(tmp_path, create=False)  # Should not raise


def test_validate_output_dir_rejects_file(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir"
    file_path.touch()

    with pytest.raises(ValueError, match="not a directory"):
        validate_output_dir(file_path)


def test_validate_output_dir_rejects_missing_no_create(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"

    with pytest.raises(ValueError, match="does not exist"):
        validate_output_dir(missing, create=False)


def test_check_disk_space_returns_bool(tmp_path: Path) -> None:
    result = check_disk_space(tmp_path, min_mb=1)
    assert isinstance(result, bool)


# ----------------------------------------------------------------------
# Manifest tests (Phase 2.3)
# ----------------------------------------------------------------------


def test_write_manifest_creates_file(tmp_path: Path) -> None:
    manifest = CrawlManifest(
        job_id="test-job-123",
        started_at="2026-01-05T00:00:00Z",
        completed_at="2026-01-05T00:01:00Z",
        config=CrawlConfig(output_dir=tmp_path, seeds=["https://example.com/"]),
        total_pages=2,
        successful=1,
        failed=1,
        skipped=0,
        duration_seconds=60.0,
        results=[
            CrawlResult(
                url="https://example.com/page1",
                file_path=tmp_path / "example.com" / "page1.md",
                status="success",
                word_count=100,
                title="Page 1",
                extracted_at="2026-01-05T00:00:30Z",
            ),
            CrawlResult(
                url="https://example.com/page2",
                file_path=None,
                status="failed",
                error="Connection timeout",
                extracted_at="2026-01-05T00:00:45Z",
            ),
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest, manifest_path)

    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text())
    assert data["job_id"] == "test-job-123"
    assert data["total_pages"] == 2
    assert data["successful"] == 1
    assert data["failed"] == 1
    assert len(data["results"]) == 2


def test_load_manifest_reads_file(tmp_path: Path) -> None:
    manifest_data = {
        "job_id": "loaded-job",
        "started_at": "2026-01-05T00:00:00Z",
        "completed_at": "2026-01-05T00:02:00Z",
        "config": {
            "output_dir": str(tmp_path),
            "seeds": ["https://example.com/"],
            "sitemaps": [],
            "allow_prefixes": [],
            "deny_prefixes": [],
            "max_pages": 50,
            "max_depth": 2,
            "concurrency": 3,
            "rate_limit_delay": 0.5,
            "follow_links": True,
        },
        "total_pages": 5,
        "successful": 4,
        "failed": 1,
        "skipped": 0,
        "duration_seconds": 120.0,
        "results": [
            {
                "url": "https://example.com/page",
                "file_path": str(tmp_path / "page.md"),
                "status": "success",
                "error": None,
                "warnings": [],
                "word_count": 200,
                "title": "Test Page",
                "extracted_at": "2026-01-05T00:01:00Z",
            }
        ],
    }

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data))

    manifest = load_manifest(manifest_path)

    assert manifest is not None
    assert manifest.job_id == "loaded-job"
    assert manifest.total_pages == 5
    assert manifest.config.max_pages == 50
    assert len(manifest.results) == 1


def test_load_manifest_returns_none_for_missing_file(tmp_path: Path) -> None:
    result = load_manifest(tmp_path / "nonexistent.json")
    assert result is None


def test_load_manifest_returns_none_for_invalid_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {")

    result = load_manifest(bad_file)
    assert result is None


def test_write_and_load_manifest_roundtrip(tmp_path: Path) -> None:
    original = CrawlManifest(
        job_id="roundtrip-test",
        started_at="2026-01-05T10:00:00Z",
        completed_at="2026-01-05T10:05:00Z",
        config=CrawlConfig(
            output_dir=tmp_path,
            seeds=["https://example.com/"],
            max_pages=10,
        ),
        total_pages=3,
        successful=2,
        failed=1,
        duration_seconds=300.0,
        results=[
            CrawlResult(
                url="https://example.com/a",
                file_path=tmp_path / "a.md",
                status="success",
                word_count=50,
                title="A",
                extracted_at="2026-01-05T10:01:00Z",
            ),
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    write_manifest(original, manifest_path)
    loaded = load_manifest(manifest_path)

    assert loaded is not None
    assert loaded.job_id == original.job_id
    assert loaded.total_pages == original.total_pages
    assert loaded.successful == original.successful
    assert len(loaded.results) == len(original.results)


# ----------------------------------------------------------------------
# run_crawl orchestrator tests
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_crawl_creates_manifest(tmp_path: Path) -> None:
    """Test run_crawl creates a manifest file."""
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = SAMPLE_HTML
        manifest = await run_crawl(config)

    assert manifest.job_id is not None
    assert manifest.started_at is not None
    assert manifest.completed_at is not None
    assert manifest.total_pages >= 0

    # Check manifest file was written
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()


@pytest.mark.asyncio
async def test_run_crawl_tracks_progress(tmp_path: Path) -> None:
    """Test run_crawl calls progress callback."""
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=False,
    )

    progress_updates: list[CrawlProgress] = []

    def on_progress(progress: CrawlProgress) -> None:
        progress_updates.append(progress)

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = SAMPLE_HTML
        await run_crawl(config, on_progress=on_progress)

    # Should have at least one progress update
    assert len(progress_updates) >= 1
    # First update should be "fetching"
    assert progress_updates[0].status == "fetching"


@pytest.mark.asyncio
async def test_run_crawl_handles_fetch_failure(tmp_path: Path) -> None:
    """Test run_crawl handles fetch failures gracefully."""
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.side_effect = Exception("Connection failed")
        manifest = await run_crawl(config)

    assert manifest.failed >= 1
    assert manifest.results[0].status == "failed"
    assert "Connection failed" in (manifest.results[0].error or "")


@pytest.mark.asyncio
async def test_run_crawl_writes_markdown_files(tmp_path: Path) -> None:
    """Test run_crawl writes markdown files for successful extractions."""
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/article"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = (SAMPLE_HTML, 200)
        manifest = await run_crawl(config)

    # Check that a markdown file was created
    md_files = list(tmp_path.glob("**/*.md"))
    assert len(md_files) >= 1

    # Verify manifest has file_path set
    successful_results = [r for r in manifest.results if r.status == "success"]
    if successful_results:
        assert successful_results[0].file_path is not None


@pytest.mark.asyncio
async def test_run_crawl_skips_empty_content(tmp_path: Path) -> None:
    """Test run_crawl marks pages with no content as skipped."""
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/empty"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_sitemaps.return_value = 0
        # Return HTML with no meaningful content
        mock_fetch.return_value = ("<html><body><nav>Menu</nav></body></html>", 200)
        manifest = await run_crawl(config)

    assert manifest.skipped >= 1


@pytest.mark.asyncio
async def test_run_crawl_honors_worker_count(tmp_path: Path) -> None:
    """run_crawl should schedule as many concurrent workers as requested."""
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=[
            "https://example.com/a",
            "https://example.com/b",
        ],
        max_pages=2,
        follow_links=False,
        concurrency=2,
        worker_count=2,
        rate_limit_delay=0.0,
    )

    in_progress = 0
    max_in_progress = 0

    async def fake_fetch(self, url, fetcher, *, max_attempts: int = 3):
        nonlocal in_progress, max_in_progress
        in_progress += 1
        max_in_progress = max(max_in_progress, in_progress)
        await asyncio.sleep(0.01)
        in_progress -= 1
        return ("<html><body><article><p>text content</p></article></body></html>", 200)

    def fake_extract(self, html, url):
        return CrawlResult(
            url=url,
            file_path=None,
            status="success",
            word_count=50,
            title="Test",
            extracted_at="now",
            markdown="# Test\n\nBody",
        )

    @asynccontextmanager
    async def fake_open_fetcher(*args, **kwargs):
        class DummyFetcher:
            async def fetch(self, url):
                return "", 200

        yield DummyFetcher()

    with (
        patch.object(Crawler, "open_fetcher", fake_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new=fake_fetch),
        patch.object(Crawler, "extract_page", new=fake_extract),
    ):
        mock_sitemaps.return_value = 0
        manifest = await run_crawl(config)

    assert manifest.successful == 2
    assert max_in_progress >= config.worker_count


def test_crawl_progress_dataclass() -> None:
    """Test CrawlProgress dataclass works correctly."""
    progress = CrawlProgress(
        url="https://example.com/",
        status="success",
        fetched=5,
        successful=4,
        failed=1,
        skipped=0,
        remaining=10,
    )

    assert progress.url == "https://example.com/"
    assert progress.status == "success"
    assert progress.fetched == 5
    assert progress.successful == 4
    assert progress.failed == 1
    assert progress.remaining == 10


def test_select_fetcher_class_prefers_explicit(tmp_path):
    from article_extractor.fetcher import HttpxFetcher

    crawler = Crawler(CrawlConfig(output_dir=tmp_path))

    assert (
        crawler._select_fetcher_class(HttpxFetcher, prefer_playwright=True)
        is HttpxFetcher
    )


@pytest.mark.asyncio
async def test_load_sitemaps_skips_filtered_urls(tmp_path: Path, monkeypatch) -> None:
    config = CrawlConfig(
        output_dir=tmp_path,
        sitemaps=["https://example.com/sitemap.xml"],
        allow_prefixes=["https://example.com/"],
    )
    crawler = Crawler(config)

    async def _fake_load(_source, _fetcher):
        return ["https://other.example.com/page"]

    monkeypatch.setattr("article_extractor.crawler.load_sitemap", _fake_load)

    enqueued = await crawler.load_sitemaps()

    assert enqueued == 0


def test_extract_page_handles_exception(tmp_path: Path, monkeypatch) -> None:
    from article_extractor import ArticleExtractor

    crawler = Crawler(CrawlConfig(output_dir=tmp_path))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("explode")

    monkeypatch.setattr(ArticleExtractor, "extract", _boom)

    result = crawler.extract_page("<html></html>", "https://example.com")

    assert result.status == "failed"
    assert "explode" in result.error


def test_extract_page_handles_unsuccessful_result(tmp_path: Path, monkeypatch) -> None:
    from article_extractor import ArticleExtractor
    from article_extractor.types import ArticleResult

    crawler = Crawler(CrawlConfig(output_dir=tmp_path))

    def _failed(*_args, **_kwargs):
        return ArticleResult(
            url="https://example.com",
            title="",
            content="",
            markdown="",
            excerpt="",
            word_count=0,
            success=False,
            error="no content",
            warnings=["warn"],
        )

    monkeypatch.setattr(ArticleExtractor, "extract", _failed)

    result = crawler.extract_page("<html></html>", "https://example.com")

    assert result.status == "failed"
    assert result.error == "no content"
    assert result.warnings == ["warn"]


def test_url_to_filepath_skips_empty_components(tmp_path: Path) -> None:
    crawler = Crawler(CrawlConfig(output_dir=tmp_path))

    path = crawler._url_to_filepath("https://example.com/@@@")

    assert path.name == "example.com__index.md"


def test_validate_output_dir_rejects_unwritable(tmp_path: Path, monkeypatch) -> None:
    from pathlib import Path as PathClass

    target = tmp_path / "unwritable"
    target.mkdir()

    original_touch = PathClass.touch

    def _boom(self, *args, **kwargs):
        if self.name == ".write_test":
            raise OSError("nope")
        return original_touch(self, *args, **kwargs)

    monkeypatch.setattr(PathClass, "touch", _boom)

    with pytest.raises(ValueError, match="not writable"):
        validate_output_dir(target)


def test_check_disk_space_handles_oserror(tmp_path: Path, monkeypatch) -> None:
    def _boom(_path):
        raise OSError("no stat")

    monkeypatch.setattr("article_extractor.crawler.os.statvfs", _boom)

    assert check_disk_space(tmp_path) is True


@pytest.mark.asyncio
async def test_load_local_sitemap_skips_remote_entries(tmp_path: Path) -> None:
    local_sitemap = tmp_path / "local.xml"
    local_sitemap.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
</urlset>
""",
        encoding="utf-8",
    )
    index = tmp_path / "index.xml"
    index.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>{local_sitemap}</loc></sitemap>
  <sitemap><loc>https://example.com/remote.xml</loc></sitemap>
</sitemapindex>
""",
        encoding="utf-8",
    )

    urls = await load_sitemap(str(index))

    assert "https://example.com/a" in urls
    assert "https://example.com/remote.xml" not in urls


def test_extract_links_handles_parser_error(monkeypatch) -> None:
    def _boom(self, _html):
        raise ValueError("bad html")

    monkeypatch.setattr("article_extractor.crawler._LinkExtractor.feed", _boom)

    assert extract_links("<html></html>", "https://example.com") == []


@pytest.mark.asyncio
async def test_run_crawl_warns_on_low_disk_space(tmp_path: Path, caplog) -> None:
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    caplog.set_level("WARNING")

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
        patch("article_extractor.crawler.check_disk_space", return_value=False),
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = SAMPLE_HTML
        await run_crawl(config)

    assert any("Low disk space" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_run_crawl_logs_sitemap_load(tmp_path: Path, caplog) -> None:
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=[],
        sitemaps=["https://example.com/sitemap.xml"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    caplog.set_level("INFO")

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_sitemaps.return_value = 1
        mock_fetch.return_value = SAMPLE_HTML
        await run_crawl(config)

    assert any(
        "Loaded 1 URLs from sitemaps" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_run_crawl_closes_when_queue_empty(tmp_path: Path, monkeypatch) -> None:
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=[],
        max_pages=1,
        follow_links=False,
    )

    called = {"closed": False}
    original_close = Crawler.close

    def _close(self):
        called["closed"] = True
        return original_close(self)

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    monkeypatch.setattr(Crawler, "close", _close)

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
    ):
        mock_sitemaps.return_value = 0
        await run_crawl(config)

    assert called["closed"] is True


@pytest.mark.asyncio
async def test_run_crawl_discovers_links_when_enabled(tmp_path: Path) -> None:
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=True,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
        patch.object(Crawler, "discover_links", return_value=0) as mock_discover,
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = (SAMPLE_HTML, 200)
        await run_crawl(config)

    mock_discover.assert_called()


@pytest.mark.asyncio
async def test_run_crawl_marks_write_failures(tmp_path: Path) -> None:
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    def _extract_page(_self, _html, _url):
        return CrawlResult(
            url="https://example.com/",
            file_path=None,
            status="success",
            word_count=10,
            title="Title",
            extracted_at="2026-01-05T10:01:00Z",
            markdown="content",
        )

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
        patch.object(Crawler, "extract_page", _extract_page),
        patch.object(Crawler, "write_markdown", side_effect=RuntimeError("boom")),
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = (SAMPLE_HTML, 200)
        manifest = await run_crawl(config)

    assert manifest.failed == 1


@pytest.mark.asyncio
async def test_run_crawl_records_failed_extractions(tmp_path: Path) -> None:
    from contextlib import asynccontextmanager

    config = CrawlConfig(
        output_dir=tmp_path,
        seeds=["https://example.com/"],
        max_pages=1,
        follow_links=False,
    )

    @asynccontextmanager
    async def mock_open_fetcher(*args, **kwargs):
        yield AsyncMock()

    def _extract_page(_self, _html, _url):
        return CrawlResult(
            url="https://example.com/",
            file_path=None,
            status="failed",
            error="nope",
            extracted_at="2026-01-05T10:01:00Z",
        )

    with (
        patch.object(Crawler, "open_fetcher", mock_open_fetcher),
        patch.object(Crawler, "load_sitemaps", new_callable=AsyncMock) as mock_sitemaps,
        patch.object(Crawler, "fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
        patch.object(Crawler, "extract_page", _extract_page),
    ):
        mock_sitemaps.return_value = 0
        mock_fetch.return_value = (SAMPLE_HTML, 200)
        manifest = await run_crawl(config)

    assert manifest.failed == 1
