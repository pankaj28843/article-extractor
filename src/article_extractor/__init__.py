"""Pure-Python article extraction library.

Extracts main content from HTML documents and converts to Markdown.
Uses JustHTML for parsing and Readability-style scoring for content detection.

No module-level caching - each extraction uses fresh instance-level caches
for safe parallel async usage.

Example:
    >>> from article_extractor import extract_article
    >>> result = extract_article(html, url="https://example.com")
    >>> print(result.title)
    >>> print(result.markdown)

For reusable extractor (slightly more efficient for multiple extractions):
    >>> from article_extractor import ArticleExtractor
    >>> extractor = ArticleExtractor()
    >>> result1 = extractor.extract(html1, url1)
    >>> result2 = extractor.extract(html2, url2)

For async URL fetching (auto-selects best fetcher):
    >>> from article_extractor import extract_article_from_url
    >>> result = await extract_article_from_url("https://example.com")

With explicit fetcher:
    >>> from article_extractor import extract_article_from_url, PlaywrightFetcher
    >>> async with PlaywrightFetcher() as fetcher:
    ...     result = await extract_article_from_url(url, fetcher)
"""

__version__ = "0.1.0"

from .extractor import ArticleExtractor, extract_article, extract_article_from_url
from .types import ArticleResult, ExtractionOptions, ScoredCandidate


# Lazy imports for optional fetchers
def __getattr__(name: str):
    """Lazy import fetchers to avoid requiring playwright/httpx."""
    if name == "PlaywrightFetcher":
        from .fetcher import PlaywrightFetcher

        return PlaywrightFetcher
    if name == "HttpxFetcher":
        from .fetcher import HttpxFetcher

        return HttpxFetcher
    if name == "get_default_fetcher":
        from .fetcher import get_default_fetcher

        return get_default_fetcher
    if name == "Fetcher":
        from .fetcher import Fetcher

        return Fetcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    "ArticleExtractor",
    "ArticleResult",
    "ExtractionOptions",
    "ScoredCandidate",
    "extract_article",
    "extract_article_from_url",
    # Lazy-loaded
    "PlaywrightFetcher",
    "HttpxFetcher",
    "get_default_fetcher",
    "Fetcher",
]
