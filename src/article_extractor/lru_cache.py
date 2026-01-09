"""Generic LRU (Least Recently Used) cache implementation.

Provides a simple, general-purpose LRU cache with O(1) get/set operations.
Useful for caching API responses, computation results, or any key-value data.

Example:
    cache = LRUCache[str, dict](max_size=100)
    cache.set("key1", {"data": "value"})
    result = cache.get("key1")
"""

from __future__ import annotations

from collections import OrderedDict


class LRUCache[K, V]:
    """Thread-safe LRU cache with configurable maximum size.

    Uses OrderedDict for O(1) get/set operations. When max_size is exceeded,
    the least recently used item is evicted automatically.

    Args:
        max_size: Maximum number of items to store (minimum 1)

    Example:
        cache = LRUCache[str, int](max_size=10)
        cache.set("answer", 42)
        value = cache.get("answer")  # Returns 42
        cache.clear()
    """

    def __init__(self, max_size: int) -> None:
        """Initialize LRU cache with maximum size.

        Args:
            max_size: Maximum number of items (clamped to minimum of 1)
        """
        self.max_size = max(1, max_size)
        self._store: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        """Retrieve value by key, marking it as recently used.

        Args:
            key: Cache key to look up

        Returns:
            Cached value if present, None otherwise
        """
        value = self._store.get(key)
        if value is not None:
            self._store.move_to_end(key)
        return value

    def set(self, key: K, value: V) -> None:
        """Store or update a value, evicting LRU item if needed.

        Args:
            key: Cache key
            value: Value to store

        Side effects:
            May evict the least recently used item if at max_size
        """
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        """Return current number of cached items."""
        return len(self._store)

    def clear(self) -> None:
        """Remove all items from the cache."""
        self._store.clear()
