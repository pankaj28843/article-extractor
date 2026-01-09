"""Main article extraction logic.

Provides:
- ArticleExtractor class: Reusable extractor with instance-level caching
- extract_article(): Convenience function for one-off extraction
- extract_article_from_url(): Async URL fetching and extraction
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Executor
from typing import TYPE_CHECKING, Protocol

from justhtml import JustHTML

from .cache import ExtractionCache
from .candidate_finder import find_top_candidate
from .constants import (
    STRIP_TAGS,
    UNLIKELY_ROLES,
)
from .content_sanitizer import sanitize_content
from .document_cleaner import clean_document
from .title_extractor import extract_title
from .types import ArticleResult, ExtractionOptions, NetworkOptions
from .url_normalizer import absolutize_urls
from .utils import extract_excerpt, get_word_count

if TYPE_CHECKING:
    pass
_STRIP_SELECTOR = ", ".join(sorted(STRIP_TAGS))
_ROLE_SELECTOR = ", ".join(f'[role="{role}"]' for role in UNLIKELY_ROLES)


class Fetcher(Protocol):
    """Protocol for HTML fetchers."""

    async def fetch(self, url: str) -> tuple[str, int]:
        """Fetch URL and return (html, status_code)."""
        ...


class ArticleExtractor:
    """Article extractor with instance-level caching.

    Thread-safe for parallel async usage - each instance maintains its own cache.

    Example:
        extractor = ArticleExtractor()
        result1 = extractor.extract(html1, url1)
        result2 = extractor.extract(html2, url2)  # Uses fresh cache

        # Or with custom options
        extractor = ArticleExtractor(ExtractionOptions(min_word_count=50))
        result = extractor.extract(html, url)
    """

    __slots__ = ("options",)

    def __init__(self, options: ExtractionOptions | None = None) -> None:
        """Initialize extractor with options.

        Args:
            options: Extraction options (uses defaults if None)
        """
        self.options = options or ExtractionOptions()

    def extract(self, html: str | bytes, url: str = "") -> ArticleResult:
        """Extract main article content from HTML.

        Creates a fresh cache for each extraction to avoid cross-document pollution.

        Args:
            html: HTML content (string or bytes)
            url: Original URL of the page

        Returns:
            ArticleResult with extracted content
        """
        # Create fresh cache for this extraction
        cache = ExtractionCache()

        try:
            return self._extract_with_cache(html, url, cache)
        finally:
            # Ensure cache is cleared even on error
            cache.clear()

    def _extract_with_cache(
        self,
        html: str | bytes,
        url: str,
        cache: ExtractionCache,
    ) -> ArticleResult:
        """Internal extraction with provided cache."""
        warnings: list[str] = []

        # Handle bytes input
        if isinstance(html, bytes):
            try:
                html = html.decode("utf-8")
            except UnicodeDecodeError:
                html = html.decode("latin-1")

        # Parse HTML
        try:
            doc = JustHTML(html)
        except Exception as e:
            return self._failure_result(
                url,
                title="",
                error=f"Failed to parse HTML: {e}",
            )

        # Clean document
        doc = clean_document(doc, _STRIP_SELECTOR, _ROLE_SELECTOR)

        # Extract title
        title = extract_title(doc, url)

        # Find main content
        top_candidate = find_top_candidate(doc, cache)

        if top_candidate is None:
            return self._failure_result(
                url,
                title=title,
                error="Could not find main content",
                warnings=warnings,
            )

        # Sanitize node before serialization to drop empty anchors/images
        if url:
            absolutize_urls(top_candidate, url)
        sanitize_content(top_candidate)

        # Extract content
        try:
            content_html = top_candidate.to_html(
                indent=2, safe=self.options.safe_markdown
            )
            markdown = top_candidate.to_markdown(safe=self.options.safe_markdown)
            text = top_candidate.to_text(separator=" ", strip=True)
        except Exception as e:
            return self._failure_result(
                url,
                title=title,
                error=f"Failed to extract content: {e}",
                warnings=warnings,
            )

        # Calculate word count
        word_count = get_word_count(text)

        # Check minimum word count
        if word_count < self.options.min_word_count:
            warnings.append(
                f"Content below minimum word count ({word_count} < {self.options.min_word_count})"
            )

        # Extract excerpt
        excerpt = extract_excerpt(text)

        return ArticleResult(
            url=url,
            title=title,
            content=content_html,
            markdown=markdown,
            excerpt=excerpt,
            word_count=word_count,
            success=True,
            warnings=warnings,
        )

    def _failure_result(
        self,
        url: str,
        *,
        title: str,
        error: str,
        warnings: list[str] | None = None,
    ) -> ArticleResult:
        """Build a failed ArticleResult with a consistent empty payload."""
        return ArticleResult(
            url=url,
            title=title,
            content="",
            markdown="",
            excerpt="",
            word_count=0,
            success=False,
            error=error,
            warnings=warnings or [],
        )


# Convenience function for backward compatibility
def extract_article(
    html: str | bytes,
    url: str = "",
    options: ExtractionOptions | None = None,
) -> ArticleResult:
    """Extract main article content from HTML.

    Convenience function that creates a fresh ArticleExtractor for each call.
    For multiple extractions, create an ArticleExtractor instance for better
    options reuse.

    Args:
        html: HTML content (string or bytes)
        url: Original URL of the page
        options: Extraction options

    Returns:
        ArticleResult with extracted content
    """
    extractor = ArticleExtractor(options)
    return extractor.extract(html, url)


# HTTP status codes where we attempt extraction if HTML looks usable
_TRANSIENT_CLIENT_STATUSES = frozenset({404, 410})

# Minimum HTML length to consider attempting extraction on transient errors
_MIN_HTML_LENGTH_FOR_TRANSIENT = 500
_HTML_HEURISTIC_MARKERS = ("<article", "<main", "</p>")


def _html_looks_extractable(html: str) -> bool:
    """Quick heuristic: does this HTML likely contain article content?"""
    if len(html) < _MIN_HTML_LENGTH_FOR_TRANSIENT:
        return False
    html_lower = html.lower()
    return any(marker in html_lower for marker in _HTML_HEURISTIC_MARKERS)


def _is_transient_error_message(error: str | None) -> bool:
    """Check whether an error message corresponds to transient statuses."""
    if not error:
        return False
    return any(str(code) in error for code in _TRANSIENT_CLIENT_STATUSES)


def _failure_result_for_url(url: str, error: str) -> ArticleResult:
    """Return a failed ArticleResult with an empty payload."""
    return ArticleResult(
        url=url,
        title="",
        content="",
        markdown="",
        excerpt="",
        word_count=0,
        success=False,
        error=error,
    )


async def extract_article_from_url(
    url: str,
    fetcher: Fetcher | None = None,
    options: ExtractionOptions | None = None,
    *,
    network: NetworkOptions | None = None,
    prefer_playwright: bool = True,
    executor: Executor | None = None,
    diagnostic_logging: bool = False,
) -> ArticleResult:
    """Fetch URL and extract article content.

    If no fetcher is provided, auto-creates one based on available packages.
    When httpx returns a transient 404/410 and Playwright is available,
    automatically retries with Playwright before failing.

    Args:
        url: URL to fetch
        fetcher: Optional fetcher instance
        options: Extraction options
        prefer_playwright: If auto-creating fetcher, prefer Playwright
        executor: Optional executor for CPU-bound parsing work
        diagnostic_logging: Enable verbose fetch diagnostics (default: False)

    Returns:
        ArticleResult with extracted content

    Example:
        # Auto-select fetcher
        result = await extract_article_from_url("https://en.wikipedia.org/wiki/Wikipedia")

        # Explicit fetcher
        async with PlaywrightFetcher() as fetcher:
            result = await extract_article_from_url("https://en.wikipedia.org/wiki/Wikipedia", fetcher)
    """
    extractor = ArticleExtractor(options)
    network = network or NetworkOptions()

    # User-provided fetcher: no fallback, honor their choice
    if fetcher is not None:
        return await _extract_with_fetcher(extractor, url, fetcher, executor)

    from .fetcher import get_default_fetcher

    try:
        fetcher_class = get_default_fetcher(prefer_playwright=prefer_playwright)
    except ImportError as e:
        return _failure_result_for_url(url, str(e))

    async with fetcher_class(
        network=network, diagnostics_enabled=diagnostic_logging
    ) as auto_fetcher:
        result = await _extract_with_fetcher(extractor, url, auto_fetcher, executor)

        # Fallback: if httpx hit a transient 404 and Playwright is available, retry
        if (
            not result.success
            and not prefer_playwright
            and _is_transient_error_message(result.error)
        ):
            from .fetcher import PlaywrightFetcher, _check_playwright

            if _check_playwright():
                async with PlaywrightFetcher(
                    network=network, diagnostics_enabled=diagnostic_logging
                ) as pw_fetcher:
                    result = await _extract_with_fetcher(
                        extractor, url, pw_fetcher, executor
                    )

        return result


async def _extract_with_fetcher(
    extractor: ArticleExtractor,
    url: str,
    fetcher: Fetcher,
    executor: Executor | None,
) -> ArticleResult:
    """Internal helper to extract with a fetcher.

    For transient client errors (404, 410), attempts extraction if the HTML
    looks substantial. Appends a warning to successful results.
    """
    try:
        html, status_code = await fetcher.fetch(url)

        # Transient client errors: try extraction if HTML looks usable
        if status_code in _TRANSIENT_CLIENT_STATUSES:
            if _html_looks_extractable(html):
                result = await _run_extraction(extractor, html, url, executor)
                if result.success:
                    result.warnings.append(
                        f"Extracted after HTTP {status_code} (SPA/client-rendered)"
                    )
                    return result
            # Extraction failed or HTML too sparse
            return _failure_result_for_url(url, f"HTTP {status_code}")

        # Other 4xx/5xx errors: fail immediately
        if status_code >= 400:
            return _failure_result_for_url(url, f"HTTP {status_code}")

        return await _run_extraction(extractor, html, url, executor)

    except Exception as e:
        return _failure_result_for_url(url, str(e))


async def _run_extraction(
    extractor: ArticleExtractor,
    html: str,
    url: str,
    executor: Executor | None,
) -> ArticleResult:
    """Execute extraction optionally in a dedicated executor."""

    if executor is None:
        return extractor.extract(html, url)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, extractor.extract, html, url)
