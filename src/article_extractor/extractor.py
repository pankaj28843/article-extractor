"""Main article extraction logic.

Provides:
- ArticleExtractor class: Reusable extractor with instance-level caching
- extract_article(): Convenience function for one-off extraction
- extract_article_from_url(): Async URL fetching and extraction
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

from justhtml import JustHTML

from .cache import ExtractionCache
from .constants import (
    MIN_CHAR_THRESHOLD,
    STRIP_TAGS,
    UNLIKELY_ROLES,
)
from .scorer import is_unlikely_candidate, rank_candidates
from .types import ArticleResult, ExtractionOptions
from .utils import extract_excerpt, get_word_count

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


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
            return ArticleResult(
                url=url,
                title="",
                content="",
                markdown="",
                excerpt="",
                word_count=0,
                success=False,
                error=f"Failed to parse HTML: {e}",
            )

        # Clean document
        doc = self._clean_document(doc)

        # Extract title
        title = self._extract_title(doc, url)

        # Find main content
        top_candidate = self._find_top_candidate(doc, cache)

        if top_candidate is None:
            return ArticleResult(
                url=url,
                title=title,
                content="",
                markdown="",
                excerpt="",
                word_count=0,
                success=False,
                error="Could not find main content",
                warnings=warnings,
            )

        # Extract content
        try:
            content_html = top_candidate.to_html(indent=2, safe=self.options.safe_markdown)
            markdown = top_candidate.to_markdown(safe=self.options.safe_markdown)
            text = top_candidate.to_text(separator=" ", strip=True)
        except Exception as e:
            return ArticleResult(
                url=url,
                title=title,
                content="",
                markdown="",
                excerpt="",
                word_count=0,
                success=False,
                error=f"Failed to extract content: {e}",
                warnings=warnings,
            )

        # Calculate word count
        word_count = get_word_count(text)

        # Check minimum word count
        if word_count < self.options.min_word_count:
            warnings.append(f"Content below minimum word count ({word_count} < {self.options.min_word_count})")

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
        # Build combined selector for all tags to strip
        strip_selector = ", ".join(STRIP_TAGS)

        # Remove all matching nodes in one query
        for node in doc.query(strip_selector):
            if hasattr(node, "parent") and node.parent:
                node.parent.remove_child(node)

        # Build combined selector for unlikely roles
        role_selector = ", ".join(f'[role="{role}"]' for role in UNLIKELY_ROLES)

        # Remove nodes with unlikely roles in one query
        for node in doc.query(role_selector):
            if hasattr(node, "parent") and node.parent:
                node.parent.remove_child(node)

        return doc

    def _find_candidates(self, doc: JustHTML, cache: ExtractionCache) -> list[SimpleDomNode]:
        """Find potential content container candidates."""
        # Look for semantic article containers first (fast path)
        candidates = [node for node in doc.query("article") if not is_unlikely_candidate(node)]

        # Add main elements
        candidates.extend(node for node in doc.query("main") if not is_unlikely_candidate(node))

        # If we found semantic containers, use them directly
        if candidates:
            return candidates

        # Fallback: scan divs and sections
        candidates.extend(
            node
            for node in doc.query("div")
            if not is_unlikely_candidate(node) and len(cache.get_node_text(node)) > MIN_CHAR_THRESHOLD
        )

        candidates.extend(
            node
            for node in doc.query("section")
            if not is_unlikely_candidate(node) and len(cache.get_node_text(node)) > MIN_CHAR_THRESHOLD
        )

        return candidates

    def _find_top_candidate(self, doc: JustHTML, cache: ExtractionCache) -> SimpleDomNode | None:
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
        if url:
            path = urlparse(url).path
            if path and path != "/":
                # Convert path to title-like string
                title = path.strip("/").split("/")[-1].replace("-", " ").replace("_", " ")
                return title.title()

        return "Untitled"


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


async def extract_article_from_url(
    url: str,
    fetcher: Fetcher | None = None,
    options: ExtractionOptions | None = None,
    *,
    prefer_playwright: bool = True,
) -> ArticleResult:
    """Fetch URL and extract article content.

    If no fetcher is provided, auto-creates one based on available packages.

    Args:
        url: URL to fetch
        fetcher: Optional fetcher instance
        options: Extraction options
        prefer_playwright: If auto-creating fetcher, prefer Playwright

    Returns:
        ArticleResult with extracted content

    Example:
        # Auto-select fetcher
        result = await extract_article_from_url("https://example.com")

        # Explicit fetcher
        async with PlaywrightFetcher() as fetcher:
            result = await extract_article_from_url("https://example.com", fetcher)
    """
    extractor = ArticleExtractor(options)

    # Auto-create fetcher if not provided
    if fetcher is None:
        from .fetcher import get_default_fetcher

        try:
            fetcher_class = get_default_fetcher(prefer_playwright=prefer_playwright)
        except ImportError as e:
            return ArticleResult(
                url=url,
                title="",
                content="",
                markdown="",
                excerpt="",
                word_count=0,
                success=False,
                error=str(e),
            )

        async with fetcher_class() as auto_fetcher:
            return await _extract_with_fetcher(extractor, url, auto_fetcher)

    return await _extract_with_fetcher(extractor, url, fetcher)


async def _extract_with_fetcher(
    extractor: ArticleExtractor,
    url: str,
    fetcher: Fetcher,
) -> ArticleResult:
    """Internal helper to extract with a fetcher."""
    try:
        html, status_code = await fetcher.fetch(url)

        if status_code >= 400:
            return ArticleResult(
                url=url,
                title="",
                content="",
                markdown="",
                excerpt="",
                word_count=0,
                success=False,
                error=f"HTTP {status_code}",
            )

        return extractor.extract(html, url)

    except Exception as e:
        return ArticleResult(
            url=url,
            title="",
            content="",
            markdown="",
            excerpt="",
            word_count=0,
            success=False,
            error=str(e),
        )
