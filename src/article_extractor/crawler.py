"""URL crawling primitives for article-extractor.

Provides a cooperative `Crawler` that manages breadth-first traversal,
URL filtering, concurrency limits, and host-level rate limiting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import defusedxml.ElementTree as ET

from .extractor import ArticleExtractor
from .fetcher import Fetcher, get_default_fetcher
from .network import resolve_network_options
from .types import CrawlConfig, CrawlManifest, CrawlResult, NetworkOptions

logger = logging.getLogger(__name__)

_SENTINEL: object = object()


@dataclass(slots=True)
class CrawlTarget:
    """An enqueued crawl target."""

    url: str
    depth: int
    parent: str | None = None


class _HostThrottle:
    """Tracks host-level rate limiting state."""

    __slots__ = ("lock", "next_available")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.next_available = 0.0


class Crawler:
    """Breadth-first crawler with filtering and rate limiting."""

    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._visited: set[str] = set()
        self._enqueued = 0
        self._closed = False
        self._max_pages = max(1, config.max_pages)
        self._max_depth = max(0, config.max_depth)
        self._allow_prefixes = tuple(
            prefix
            for value in config.allow_prefixes
            if (prefix := self._normalize_prefix(value))
        )
        self._deny_prefixes = tuple(
            prefix
            for value in config.deny_prefixes
            if (prefix := self._normalize_prefix(value))
        )
        self._semaphore = asyncio.Semaphore(max(1, config.concurrency))
        self._host_limits: dict[str, _HostThrottle] = {}

        for seed in config.seeds:
            self.enqueue_url(seed, depth=0)

    # ------------------------------------------------------------------
    # Fetcher orchestration
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def open_fetcher(
        self,
        *,
        prefer_playwright: bool = True,
        network: NetworkOptions | None = None,
        fetcher_cls: type[Fetcher] | None = None,
        **fetcher_kwargs: Any,
    ) -> AsyncIterator[Fetcher]:
        """Yield a fetcher instance honoring network preferences."""

        selected_cls = self._select_fetcher_class(fetcher_cls, prefer_playwright)
        resolved_network = self._resolve_network(network)
        fetcher = selected_cls(network=resolved_network, **fetcher_kwargs)
        async with fetcher as active:
            yield active

    async def fetch_with_retry(
        self,
        url: str,
        fetcher: Fetcher,
        *,
        max_attempts: int = 3,
    ) -> tuple[str, int]:
        """Fetch a URL with concurrency controls and retries."""

        attempts_allowed = max(1, max_attempts)
        attempt = 1
        while True:
            try:
                async with self.acquire_slot(url):
                    return await fetcher.fetch(url)
            except Exception as exc:
                if attempt >= attempts_allowed:
                    logger.error(
                        "Fetch failed after %s attempts", attempt, exc_info=exc
                    )
                    raise
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Fetch attempt %s failed; retrying in %.2fs",
                    attempt,
                    delay,
                    extra={"url": url, "error": exc.__class__.__name__},
                )
                await asyncio.sleep(delay)
                attempt += 1

    def _select_fetcher_class(
        self,
        fetcher_cls: type[Fetcher] | None,
        prefer_playwright: bool,
    ) -> type[Fetcher]:
        if fetcher_cls is not None:
            return fetcher_cls
        return get_default_fetcher(prefer_playwright)

    def _resolve_network(self, network: NetworkOptions | None) -> NetworkOptions:
        return network if network is not None else resolve_network_options()

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(0.3 * attempt, 1.5)

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def enqueue_url(self, url: str, *, depth: int, parent: str | None = None) -> bool:
        """Attempt to enqueue a URL respecting filters and limits."""

        try:
            normalized = self._normalize_url(url)
        except ValueError:
            logger.debug("Skipping invalid URL: %s", url)
            return False

        if not self._should_enqueue(normalized, depth):
            return False

        target = CrawlTarget(url=normalized, depth=depth, parent=parent)
        self._queue.put_nowait(target)
        self._visited.add(normalized)
        self._enqueued += 1
        logger.debug("Enqueued %s at depth %s", normalized, depth)
        return True

    async def get_next_target(self) -> CrawlTarget | None:
        """Return the next crawl target or None when closed."""

        item = await self._queue.get()
        if item is _SENTINEL:
            # Reinsert sentinel for other consumers.
            self._queue.put_nowait(_SENTINEL)
            self._queue.task_done()
            return None
        return item  # type: ignore[return-value]

    async def iter_targets(self) -> AsyncIterator[CrawlTarget]:
        """Yield targets until the crawler is closed."""

        while True:
            target = await self.get_next_target()
            if target is None:
                break
            yield target

    def task_done(self) -> None:
        """Mark the current queue item as processed."""

        self._queue.task_done()

    def close(self) -> None:
        """Signal that no more URLs will be enqueued."""

        if self._closed:
            return
        self._closed = True
        self._queue.put_nowait(_SENTINEL)

    # ------------------------------------------------------------------
    # Filtering helpers
    # ------------------------------------------------------------------
    def _should_enqueue(self, url: str, depth: int) -> bool:
        if depth > self._max_depth:
            return False
        if url in self._visited:
            return False
        if self._enqueued >= self._max_pages:
            return False
        if not self._matches_allow_list(url):
            return False
        return not self._matches_deny_list(url)

    def _matches_allow_list(self, url: str) -> bool:
        if not self._allow_prefixes:
            return True
        return any(url.startswith(prefix) for prefix in self._allow_prefixes)

    def _matches_deny_list(self, url: str) -> bool:
        if not self._deny_prefixes:
            return False
        return any(url.startswith(prefix) for prefix in self._deny_prefixes)

    # ------------------------------------------------------------------
    # Concurrency + rate limiting
    # ------------------------------------------------------------------
    @asynccontextmanager
    async def acquire_slot(self, url: str) -> AsyncIterator[None]:
        """Acquire a concurrency slot and honor host-level throttling."""

        async with self._semaphore:
            await self._throttle_host(self._host_key(url))
            yield

    async def _throttle_host(self, host: str | None) -> None:
        if not host or self.config.rate_limit_delay <= 0:
            return

        limiter = self._host_limits.setdefault(host, _HostThrottle())
        async with limiter.lock:
            now = time.monotonic()
            wait_for = max(0.0, limiter.next_available - now)
            if wait_for:
                await asyncio.sleep(wait_for)
            limiter.next_available = (
                max(now, limiter.next_available) + self.config.rate_limit_delay
            )

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------
    def queue_size(self) -> int:
        return self._queue.qsize()

    def total_enqueued(self) -> int:
        return self._enqueued

    def visited_urls(self) -> set[str]:
        return set(self._visited)

    def has_capacity(self) -> bool:
        return self._enqueued < self._max_pages

    # ------------------------------------------------------------------
    # Link discovery integration
    # ------------------------------------------------------------------
    def discover_links(self, html: str, base_url: str, parent_depth: int) -> int:
        """Extract links from HTML and enqueue those passing filters.

        Args:
            html: HTML content to parse for links.
            base_url: URL of the page (for resolving relative links).
            parent_depth: Depth of the parent page.

        Returns:
            Number of new URLs successfully enqueued.
        """
        if not self.config.follow_links:
            return 0

        links = extract_links(html, base_url)
        enqueued = 0
        for link in links:
            if self.enqueue_url(link, depth=parent_depth + 1, parent=base_url):
                enqueued += 1
        return enqueued

    async def load_sitemaps(self, fetcher: Fetcher | None = None) -> int:
        """Load all configured sitemaps and enqueue discovered URLs.

        Args:
            fetcher: Fetcher instance for remote sitemaps.

        Returns:
            Number of new URLs successfully enqueued from sitemaps.
        """
        enqueued = 0
        for source in self.config.sitemaps:
            urls = await load_sitemap(source, fetcher)
            for url in urls:
                if self.enqueue_url(url, depth=0):
                    enqueued += 1
        return enqueued

    # ------------------------------------------------------------------
    # Extraction pipeline
    # ------------------------------------------------------------------
    def extract_page(self, html: str, url: str) -> CrawlResult:
        """Extract article content from fetched HTML.

        Args:
            html: Raw HTML content.
            url: URL of the page.

        Returns:
            CrawlResult with extraction outcome.
        """
        extractor = ArticleExtractor()
        now = datetime.now(UTC).isoformat()

        try:
            result = extractor.extract(html, url)
        except Exception as exc:
            logger.warning("Extraction failed for %s: %s", url, exc)
            return CrawlResult(
                url=url,
                file_path=None,
                status="failed",
                error=str(exc),
                extracted_at=now,
            )

        if not result.success:
            return CrawlResult(
                url=url,
                file_path=None,
                status="failed",
                error=result.error or "Extraction unsuccessful",
                warnings=result.warnings,
                extracted_at=now,
            )

        return CrawlResult(
            url=url,
            file_path=None,  # Set by write_markdown
            status="success",
            warnings=result.warnings,
            word_count=result.word_count,
            title=result.title,
            extracted_at=now,
            markdown=result.markdown,
        )

    def write_markdown(
        self,
        url: str,
        title: str,
        markdown: str,
        word_count: int,
        extracted_at: str,
    ) -> Path:
        """Write extracted content to a Markdown file.

        Creates flat structure: {output_dir}/{hostname}__{path-slug}.md
        Path separators (/) are replaced with double underscores (__).

        Args:
            url: Original page URL.
            title: Extracted article title.
            markdown: Markdown content.
            word_count: Word count of extracted content.
            extracted_at: ISO timestamp of extraction.

        Returns:
            Path to the written file.
        """
        file_path = self._url_to_filepath(url)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        frontmatter = f"""---
url: {url}
title: "{title.replace('"', '\\"')}"
extracted_at: {extracted_at}
word_count: {word_count}
---

"""
        file_path.write_text(frontmatter + markdown, encoding="utf-8")
        logger.debug("Wrote %s", file_path)
        return file_path

    def _url_to_filepath(self, url: str) -> Path:
        """Generate a deterministic flat file path from a URL.

        Path separators (/) are replaced with double underscores (__) to create
        a flat output structure. The hostname is prepended to ensure uniqueness
        across different domains.

        Example:
            https://example.com/blog/post-1 -> example.com__blog__post-1.md
        """
        parsed = urlsplit(url)
        hostname = parsed.netloc.lower().replace(":", "_")
        path = parsed.path.strip("/") or "index"
        if parsed.query:
            path = f"{path}_{parsed.query}"

        # Split path into components and sanitize each individually
        components = path.split("/")
        sanitized_components = []
        for component in components:
            # Sanitize each component: keep alphanumeric, hyphens
            slug = re.sub(r"[^\w\-]", "_", component)
            slug = re.sub(r"_+", "_", slug)
            slug = slug.strip("_")
            if slug:
                sanitized_components.append(slug)

        # Join components with __ and prepend hostname
        path_slug = "__".join(sanitized_components) if sanitized_components else "index"
        flat_name = f"{hostname}__{path_slug}.md"

        return self.config.output_dir / flat_name

    # ------------------------------------------------------------------
    # Normalization helpers
    # ------------------------------------------------------------------
    def _normalize_prefix(self, value: str) -> str:
        try:
            return self._normalize_url(value)
        except ValueError:
            logger.debug("Ignoring invalid prefix: %s", value)
            return ""

    def _normalize_url(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("blank URL")

        parsed = urlsplit(value)
        if not parsed.scheme:
            parsed = urlsplit(f"http://{value}")
        if not parsed.netloc:
            raise ValueError(f"URL missing host: {value}")

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        query = parsed.query
        return urlunsplit((scheme, netloc, path, query, ""))

    def _host_key(self, url: str) -> str | None:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        return parsed.netloc.lower() if parsed.netloc else None


# ----------------------------------------------------------------------
# Output directory validation
# ----------------------------------------------------------------------


def validate_output_dir(path: Path, *, create: bool = True) -> None:
    """Validate that output directory is usable.

    Args:
        path: Directory path to validate.
        create: Whether to create the directory if it doesn't exist.

    Raises:
        ValueError: If path is invalid or not writable.
    """
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Output path exists but is not a directory: {path}")
        # Check writability
        test_file = path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except OSError as exc:
            raise ValueError(f"Output directory is not writable: {path}") from exc
    elif create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Cannot create output directory: {path}") from exc
    else:
        raise ValueError(f"Output directory does not exist: {path}")


def check_disk_space(path: Path, min_mb: int = 100) -> bool:
    """Check if sufficient disk space is available.

    Args:
        path: Directory to check.
        min_mb: Minimum required space in megabytes.

    Returns:
        True if sufficient space available, False otherwise.
    """
    try:
        stat = os.statvfs(path)
        available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
        return available_mb >= min_mb
    except OSError:
        # Cannot determine - assume OK
        return True


# ----------------------------------------------------------------------
# Manifest generation
# ----------------------------------------------------------------------


def _config_to_dict(config: CrawlConfig) -> dict[str, Any]:
    """Convert CrawlConfig to JSON-serializable dict."""
    return {
        "output_dir": str(config.output_dir),
        "seeds": config.seeds,
        "sitemaps": config.sitemaps,
        "allow_prefixes": config.allow_prefixes,
        "deny_prefixes": config.deny_prefixes,
        "max_pages": config.max_pages,
        "max_depth": config.max_depth,
        "concurrency": config.concurrency,
        "worker_count": config.worker_count,
        "rate_limit_delay": config.rate_limit_delay,
        "follow_links": config.follow_links,
    }


def _result_to_dict(result: CrawlResult) -> dict[str, Any]:
    """Convert CrawlResult to JSON-serializable dict."""
    return {
        "url": result.url,
        "file_path": str(result.file_path) if result.file_path else None,
        "status": result.status,
        "error": result.error,
        "warnings": result.warnings,
        "word_count": result.word_count,
        "title": result.title,
        "extracted_at": result.extracted_at,
    }


def write_manifest(manifest: CrawlManifest, path: Path) -> None:
    """Write manifest to JSON file.

    Args:
        manifest: Crawl manifest to serialize.
        path: Output file path.
    """
    data = {
        "job_id": manifest.job_id,
        "started_at": manifest.started_at,
        "completed_at": manifest.completed_at,
        "config": _config_to_dict(manifest.config),
        "total_pages": manifest.total_pages,
        "successful": manifest.successful,
        "failed": manifest.failed,
        "skipped": manifest.skipped,
        "duration_seconds": manifest.duration_seconds,
        "results": [_result_to_dict(r) for r in manifest.results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Wrote manifest to %s", path)


def load_manifest(path: Path) -> CrawlManifest | None:
    """Load existing manifest for incremental updates.

    Args:
        path: Manifest file path.

    Returns:
        Loaded manifest or None if not found/invalid.
    """
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        config = CrawlConfig(
            output_dir=Path(data["config"]["output_dir"]),
            seeds=data["config"].get("seeds", []),
            sitemaps=data["config"].get("sitemaps", []),
            allow_prefixes=data["config"].get("allow_prefixes", []),
            deny_prefixes=data["config"].get("deny_prefixes", []),
            max_pages=data["config"].get("max_pages", 100),
            max_depth=data["config"].get("max_depth", 3),
            concurrency=data["config"].get("concurrency", 5),
            worker_count=data["config"].get("worker_count", 1),
            rate_limit_delay=data["config"].get("rate_limit_delay", 1.0),
            follow_links=data["config"].get("follow_links", True),
        )
        results = [
            CrawlResult(
                url=r["url"],
                file_path=Path(r["file_path"]) if r["file_path"] else None,
                status=r["status"],
                error=r.get("error"),
                warnings=r.get("warnings", []),
                word_count=r.get("word_count", 0),
                title=r.get("title", ""),
                extracted_at=r.get("extracted_at", ""),
            )
            for r in data.get("results", [])
        ]
        return CrawlManifest(
            job_id=data["job_id"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            config=config,
            total_pages=data.get("total_pages", 0),
            successful=data.get("successful", 0),
            failed=data.get("failed", 0),
            skipped=data.get("skipped", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            results=results,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Failed to load manifest from %s: %s", path, exc)
        return None


# ----------------------------------------------------------------------
# Sitemap parsing utilities
# ----------------------------------------------------------------------

_SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
}


def parse_sitemap_xml(xml_content: str) -> list[str]:
    """Extract URLs from sitemap XML (<urlset> or <sitemapindex>).

    Returns a list of URLs found in <loc> elements. For <sitemapindex>,
    returns the nested sitemap URLs (caller must fetch and parse them).
    """
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.warning("Failed to parse sitemap XML: %s", exc)
        return urls

    # Handle both namespaced and non-namespaced elements
    for loc in root.iter():
        tag_name = loc.tag.split("}")[-1] if "}" in loc.tag else loc.tag
        if tag_name == "loc" and loc.text:
            urls.append(loc.text.strip())

    return urls


def is_sitemap_index(xml_content: str) -> bool:
    """Check if the XML is a sitemapindex (contains nested sitemaps)."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return False

    tag_name = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    return tag_name == "sitemapindex"


async def load_sitemap(
    source: str,
    fetcher: Fetcher | None = None,
) -> list[str]:
    """Load URLs from a sitemap source (local file or remote URL).

    For sitemapindex files, recursively fetches nested sitemaps.
    Returns a flat list of all discovered page URLs.
    """
    if _is_local_path(source):
        return await _load_local_sitemap(source)
    return await _load_remote_sitemap(source, fetcher)


def _is_local_path(source: str) -> bool:
    """Determine if source is a local file path vs URL."""
    if source.startswith(("http://", "https://")):
        return False
    # Treat as local if it looks like a path
    return "/" in source or source.endswith(".xml") or Path(source).exists()


async def _load_local_sitemap(path: str) -> list[str]:
    """Read and parse a local sitemap file."""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read local sitemap %s: %s", path, exc)
        return []

    urls = parse_sitemap_xml(content)
    if is_sitemap_index(content):
        # Recursively load nested sitemaps (local files only)
        nested: list[str] = []
        for sitemap_url in urls:
            if _is_local_path(sitemap_url):
                nested.extend(await _load_local_sitemap(sitemap_url))
            else:
                logger.debug("Skipping remote sitemap in local index: %s", sitemap_url)
        return nested
    return urls


async def _load_remote_sitemap(
    url: str,
    fetcher: Fetcher | None,
) -> list[str]:
    """Fetch and parse a remote sitemap URL."""
    if fetcher is None:
        logger.warning("No fetcher provided for remote sitemap: %s", url)
        return []

    try:
        content, status = await fetcher.fetch(url)
    except Exception as exc:
        logger.warning("Failed to fetch sitemap %s: %s", url, exc)
        return []

    if status >= 400:
        logger.warning("Sitemap fetch returned status %s: %s", status, url)
        return []

    urls = parse_sitemap_xml(content)
    if is_sitemap_index(content):
        # Recursively fetch nested sitemaps
        nested: list[str] = []
        for sitemap_url in urls:
            nested.extend(await _load_remote_sitemap(sitemap_url, fetcher))
        return nested
    return urls


# ----------------------------------------------------------------------
# Link discovery
# ----------------------------------------------------------------------


class _LinkExtractor(HTMLParser):
    """Extract href values from anchor tags."""

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                resolved = urljoin(self.base_url, value)
                # Only keep http(s) links
                if resolved.startswith(("http://", "https://")):
                    self.links.append(resolved)
                break


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract absolute HTTP(S) links from HTML content.

    Args:
        html: Raw HTML content to parse.
        base_url: Base URL for resolving relative hrefs.

    Returns:
        List of absolute URLs found in <a href> elements.
    """
    parser = _LinkExtractor(base_url)
    try:
        parser.feed(html)
    except Exception as exc:
        logger.debug("Link extraction failed: %s", exc)
    return parser.links


# ----------------------------------------------------------------------
# High-level crawl orchestration
# ----------------------------------------------------------------------


@dataclass
class CrawlProgress:
    """Progress update during crawl."""

    url: str
    status: str  # "fetching", "success", "failed", "skipped"
    fetched: int
    successful: int
    failed: int
    skipped: int
    remaining: int


async def run_crawl(  # noqa: PLR0915
    config: CrawlConfig,
    *,
    network: NetworkOptions | None = None,
    on_progress: Callable[[CrawlProgress], None] | None = None,
) -> CrawlManifest:
    """Run a complete crawl job using a configurable pool of workers."""

    import uuid

    job_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    results: list[CrawlResult] = []
    successful = 0
    failed = 0
    skipped = 0
    worker_count = max(1, config.worker_count)

    validate_output_dir(config.output_dir, create=True)
    if not check_disk_space(config.output_dir):
        logger.warning("Low disk space in output directory: %s", config.output_dir)

    crawler = Crawler(config)
    progress_lock = asyncio.Lock()
    active_lock = asyncio.Lock()
    active_workers = 0

    async def emit_progress(status: str, url: str) -> None:
        if on_progress is None:
            return
        async with progress_lock:
            on_progress(
                CrawlProgress(
                    url=url,
                    status=status,
                    fetched=successful + failed + skipped,
                    successful=successful,
                    failed=failed,
                    skipped=skipped,
                    remaining=crawler.queue_size(),
                )
            )

    async def mark_worker_start() -> None:
        nonlocal active_workers
        async with active_lock:
            active_workers += 1

    async def mark_worker_end() -> None:
        nonlocal active_workers
        async with active_lock:
            active_workers -= 1
            if crawler.queue_size() == 0 and active_workers == 0:
                crawler.close()

    async with crawler.open_fetcher(network=network) as fetcher:
        sitemap_count = await crawler.load_sitemaps(fetcher)
        if sitemap_count > 0:
            logger.info("Loaded %d URLs from sitemaps", sitemap_count)

        if crawler.queue_size() == 0:
            crawler.close()

        async def worker() -> None:
            nonlocal successful, failed, skipped
            async for target in crawler.iter_targets():
                await mark_worker_start()
                try:
                    await emit_progress("fetching", target.url)
                    try:
                        async with crawler.acquire_slot(target.url):
                            html, _status = await crawler.fetch_with_retry(
                                target.url,
                                fetcher=fetcher,
                            )
                    except Exception as exc:
                        logger.warning("Fetch failed for %s: %s", target.url, exc)
                        failure = CrawlResult(
                            url=target.url,
                            file_path=None,
                            status="failed",
                            error=str(exc),
                            extracted_at=datetime.now(UTC).isoformat(),
                        )
                        results.append(failure)
                        failed += 1
                        await emit_progress("failed", target.url)
                        continue

                    if config.follow_links:
                        crawler.discover_links(html, target.url, target.depth)

                    page_result = crawler.extract_page(html, target.url)

                    if page_result.status == "success" and page_result.word_count > 0:
                        try:
                            file_path = crawler.write_markdown(
                                url=page_result.url,
                                title=page_result.title or "",
                                markdown=page_result.markdown or "",
                                word_count=page_result.word_count,
                                extracted_at=page_result.extracted_at,
                            )
                            page_result = replace(page_result, file_path=file_path)
                            successful += 1
                        except Exception as exc:
                            logger.warning(
                                "Failed to write markdown for %s: %s",
                                page_result.url,
                                exc,
                            )
                            page_result = CrawlResult(
                                url=page_result.url,
                                file_path=None,
                                status="failed",
                                error=f"Write failed: {exc}",
                                extracted_at=page_result.extracted_at,
                            )
                            failed += 1
                    elif page_result.status == "success":
                        page_result = CrawlResult(
                            url=page_result.url,
                            file_path=None,
                            status="skipped",
                            error="No content extracted",
                            extracted_at=page_result.extracted_at,
                            markdown=page_result.markdown,
                            warnings=page_result.warnings,
                            word_count=page_result.word_count,
                            title=page_result.title,
                        )
                        skipped += 1
                    else:
                        failed += 1

                    results.append(page_result)
                    await emit_progress(page_result.status, target.url)
                finally:
                    crawler.task_done()
                    await mark_worker_end()

        async with asyncio.TaskGroup() as tg:
            for _ in range(worker_count):
                tg.create_task(worker())

    completed_at = datetime.now(UTC).isoformat()
    duration = (
        datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
    ).total_seconds()

    manifest = CrawlManifest(
        job_id=job_id,
        started_at=started_at,
        completed_at=completed_at,
        config=config,
        total_pages=len(results),
        successful=successful,
        failed=failed,
        skipped=skipped,
        duration_seconds=duration,
        results=results,
    )

    manifest_path = config.output_dir / "manifest.json"
    write_manifest(manifest, manifest_path)
    logger.info(
        "Crawl complete",
        extra={
            "job_id": job_id,
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "duration_seconds": duration,
        },
    )

    return manifest
