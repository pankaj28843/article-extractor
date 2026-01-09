"""Extraction response cache with thread-safe async operations.

Wraps LRUCache with async lock coordination and encapsulates cache key
construction logic, hiding internal representation from callers.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .lru_cache import LRUCache

if TYPE_CHECKING:
    from .types import ExtractionOptions


class ExtractionCache:
    """Thread-safe async cache for extraction responses.

    Encapsulates cache key construction and lock acquisition, providing
    a simple interface for storing and retrieving extraction responses.
    """

    def __init__(self, max_size: int = 100) -> None:
        """Initialize cache with maximum size.

        Args:
            max_size: Maximum number of entries to cache
        """
        self._cache: LRUCache[str, dict] = LRUCache(max_size=max_size)
        self._lock = asyncio.Lock()

    def _build_key(self, url: str, options: ExtractionOptions) -> str:
        """Build cache key from URL and extraction options.

        Args:
            url: URL being extracted
            options: Extraction options that affect output

        Returns:
            Cache key incorporating all relevant parameters
        """
        return "|".join(
            [
                url,
                str(options.min_word_count),
                str(options.min_char_threshold),
                "1" if options.include_images else "0",
                "1" if options.include_code_blocks else "0",
                "1" if options.safe_markdown else "0",
            ]
        )

    async def lookup(self, url: str, options: ExtractionOptions) -> dict | None:
        """Retrieve cached extraction response if available.

        Args:
            url: URL to look up
            options: Extraction options used for cache key

        Returns:
            Cached response dict or None if not found
        """
        key = self._build_key(url, options)
        async with self._lock:
            return self._cache.get(key)

    async def store(self, url: str, options: ExtractionOptions, response: dict) -> None:
        """Store extraction response in cache.

        Args:
            url: URL being cached
            options: Extraction options used for cache key
            response: Response dict to cache
        """
        key = self._build_key(url, options)
        async with self._lock:
            self._cache.set(key, response)

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Return current cache size (number of entries)."""
        return len(self._cache)

    @property
    def max_size(self) -> int:
        """Return maximum cache size."""
        return self._cache.max_size
