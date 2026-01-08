"""Main article extraction logic.

Provides:
- ArticleExtractor class: Reusable extractor with instance-level caching
- extract_article(): Convenience function for one-off extraction
- extract_article_from_url(): Async URL fetching and extraction
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Executor
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urljoin, urlparse

from justhtml import JustHTML

from .cache import ExtractionCache
from .constants import (
    MIN_CHAR_THRESHOLD,
    STRIP_TAGS,
    UNLIKELY_ROLES,
)
from .scorer import is_unlikely_candidate, rank_candidates
from .types import ArticleResult, ExtractionOptions, NetworkOptions
from .utils import extract_excerpt, get_word_count

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


_URL_ATTR_MAP: dict[str, tuple[str, ...]] = {
    "a": ("href",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
}
_STRIP_SELECTOR = ", ".join(sorted(STRIP_TAGS))
_ROLE_SELECTOR = ", ".join(f'[role="{role}"]' for role in UNLIKELY_ROLES)
_SEMANTIC_CANDIDATE_TAGS = ("article", "main")
_FALLBACK_CANDIDATE_TAGS = ("div", "section")


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
        doc = self._clean_document(doc)

        # Extract title
        title = self._extract_title(doc, url)

        # Find main content
        top_candidate = self._find_top_candidate(doc, cache)

        if top_candidate is None:
            return self._failure_result(
                url,
                title=title,
                error="Could not find main content",
                warnings=warnings,
            )

        # Sanitize node before serialization to drop empty anchors/images
        if url:
            self._absolutize_urls(top_candidate, url)
        self._sanitize_content_node(top_candidate)

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

    def _clean_document(self, doc: JustHTML) -> JustHTML:
        """Remove scripts, styles, and other non-content elements."""
        self._remove_nodes_by_selector(doc, _STRIP_SELECTOR)
        self._remove_nodes_by_selector(doc, _ROLE_SELECTOR)

        return doc

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

    def _remove_nodes_by_selector(self, doc: JustHTML, selector: str) -> None:
        """Remove all nodes matching a selector when they have a parent."""
        for node in doc.query(selector):
            parent = getattr(node, "parent", None)
            if parent is not None:
                parent.remove_child(node)

    def _find_candidates(
        self, doc: JustHTML, cache: ExtractionCache
    ) -> list[SimpleDomNode]:
        """Find potential content container candidates."""
        # Look for semantic article containers first (fast path)
        candidates: list[SimpleDomNode] = []
        for tag in _SEMANTIC_CANDIDATE_TAGS:
            candidates.extend(self._candidate_nodes(doc, cache, tag))

        # If we found semantic containers, use them directly
        if candidates:
            return candidates

        # Fallback: scan divs and sections
        for tag in _FALLBACK_CANDIDATE_TAGS:
            candidates.extend(
                self._candidate_nodes(doc, cache, tag, min_length=MIN_CHAR_THRESHOLD)
            )

        return candidates

    def _candidate_nodes(
        self,
        doc: JustHTML,
        cache: ExtractionCache,
        tag: str,
        *,
        min_length: int | None = None,
    ) -> list[SimpleDomNode]:
        """Collect candidate nodes for a tag with optional length filtering."""
        candidates: list[SimpleDomNode] = []
        for node in doc.query(tag):
            if is_unlikely_candidate(node):
                continue
            if min_length is not None and cache.get_text_length(node) <= min_length:
                continue
            candidates.append(node)
        return candidates

    def _find_top_candidate(
        self, doc: JustHTML, cache: ExtractionCache
    ) -> SimpleDomNode | None:
        """Find the best content container using Readability algorithm."""
        candidates = self._find_candidates(doc, cache)

        if not candidates:
            # Fallback: look for body
            body_nodes = doc.query("body")
            if body_nodes:
                candidates = [body_nodes[0]]

        if not candidates:
            return None

        # Rank candidates by content score
        ranked = rank_candidates(candidates, cache)

        if not ranked:
            return None

        # Return the top candidate
        return ranked[0].node

    def _extract_title(self, doc: JustHTML, url: str = "") -> str:
        """Extract title using cascading fallbacks."""
        # Try og:title
        og_title = doc.query('meta[property="og:title"]')
        if og_title:
            content = og_title[0].attrs.get("content", "")
            if content:
                return str(content)

        # Try first h1
        h1_nodes = doc.query("h1")
        if h1_nodes:
            h1_text = h1_nodes[0].to_text(strip=True)
            if h1_text:
                return h1_text

        # Try <title> tag
        title_nodes = doc.query("title")
        if title_nodes:
            title_text = title_nodes[0].to_text(strip=True)
            if title_text:
                # Clean common suffixes like " - Site Name"
                if " - " in title_text:
                    title_text = title_text.split(" - ")[0].strip()
                return title_text

        # Fallback to URL
        url_title = self._title_from_url(url)
        if url_title:
            return url_title

        return "Untitled"

    def _title_from_url(self, url: str) -> str | None:
        """Build a readable title from a URL path."""

        if not url:
            return None

        path = urlparse(url).path
        if not path or path == "/":
            return None

        title = path.strip("/").split("/")[-1].replace("-", " ").replace("_", " ")
        return title.title()

    def _sanitize_content_node(self, node: SimpleDomNode) -> None:
        """Remove empty anchors and images without usable sources."""

        self._remove_empty_links(node)
        self._remove_empty_images(node)
        self._remove_empty_blocks(node)

    def _collect_nodes(
        self, root: SimpleDomNode, tags: tuple[str, ...]
    ) -> list[SimpleDomNode]:
        """Return nodes matching tags, including the root if applicable."""
        nodes: list[SimpleDomNode] = []
        for tag in tags:
            nodes.extend(root.query(tag))

        root_tag = getattr(root, "name", "").lower()
        if root_tag in tags:
            nodes.append(root)

        return nodes

    def _absolutize_urls(self, node: SimpleDomNode, base_url: str) -> None:
        """Rewrite relative media/anchor URLs inside the node to be absolute."""

        for tag, attributes in _URL_ATTR_MAP.items():
            for element in self._collect_nodes(node, (tag,)):
                self._rewrite_url_attributes(element, attributes, base_url)

    def _rewrite_url_attributes(
        self,
        element: SimpleDomNode,
        attributes: tuple[str, ...],
        base_url: str,
    ) -> None:
        attrs = getattr(element, "attrs", None)
        if not attrs:
            return

        for attribute in attributes:
            value = attrs.get(attribute)
            if not value:
                continue
            if attribute == "srcset":
                attrs[attribute] = self._normalize_srcset(value, base_url)
            else:
                attrs[attribute] = urljoin(base_url, str(value))

    def _normalize_srcset(self, value: str, base_url: str) -> str:
        entries: list[str] = []
        for raw_entry in str(value).split(","):
            candidate = raw_entry.strip()
            if not candidate:
                continue
            if " " in candidate:
                url_part, descriptor = candidate.split(None, 1)
                entries.append(f"{urljoin(base_url, url_part)} {descriptor.strip()}")
            else:
                entries.append(urljoin(base_url, candidate))
        return ", ".join(entries)

    def _remove_empty_links(self, root: SimpleDomNode) -> None:
        """Drop anchor tags that would render as empty markdown links."""

        self._remove_nodes(root, ("a",), keep=self._node_has_visible_content)

    def _remove_empty_images(self, root: SimpleDomNode) -> None:
        """Remove <img> elements without a usable src attribute."""

        self._remove_nodes(root, ("img",), keep=self._has_valid_image_src)

    def _remove_nodes(
        self,
        root: SimpleDomNode,
        tags: tuple[str, ...],
        *,
        keep: Callable[[SimpleDomNode], bool],
    ) -> None:
        """Remove nodes for tags when they fail the keep predicate."""

        for node in self._collect_nodes(root, tags):
            if keep(node):
                continue

            parent = getattr(node, "parent", None)
            if parent is not None:
                parent.remove_child(node)

    def _has_valid_image_src(self, node: SimpleDomNode) -> bool:
        """Check whether an image node has a non-empty src attribute."""

        attrs = getattr(node, "attrs", {}) or {}
        src = attrs.get("src")
        if src is None:
            return False

        return bool(str(src).strip())

    def _remove_empty_blocks(self, root: SimpleDomNode) -> None:
        """Strip block-level nodes that no longer carry content."""

        target_tags = ("li", "p", "div")
        self._remove_nodes(root, target_tags, keep=self._node_has_visible_content)

    def _node_has_visible_content(self, node: SimpleDomNode) -> bool:
        """Determine whether a node contains text or media worth keeping."""

        text = node.to_text(strip=True)
        if text:
            return True

        return any(self._has_valid_image_src(img) for img in node.query("img"))


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


def _http_error_result(url: str, status_code: int) -> ArticleResult:
    return _failure_result_for_url(url, f"HTTP {status_code}")


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
            return _http_error_result(url, status_code)

        # Other 4xx/5xx errors: fail immediately
        if status_code >= 400:
            return _http_error_result(url, status_code)

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
