"""Tests for generic LRU cache module."""

from article_extractor.lru_cache import LRUCache


def test_lru_cache_basic_operations():
    """Test basic get/set operations."""
    cache = LRUCache[str, int](max_size=3)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 3


def test_lru_cache_eviction():
    """Test LRU eviction when max_size is exceeded."""
    cache = LRUCache[str, str](max_size=2)

    cache.set("first", "value1")
    cache.set("second", "value2")
    cache.set("third", "value3")  # Should evict "first"

    assert cache.get("first") is None
    assert cache.get("second") == "value2"
    assert cache.get("third") == "value3"
    assert len(cache) == 2


def test_lru_cache_access_updates_order():
    """Test that accessing an item moves it to the end (most recent)."""
    cache = LRUCache[str, int](max_size=2)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # Access "a", making it most recent
    cache.set("c", 3)  # Should evict "b", not "a"

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_lru_cache_update_existing_key():
    """Test updating an existing key."""
    cache = LRUCache[str, int](max_size=3)

    cache.set("key", 100)
    assert cache.get("key") == 100

    cache.set("key", 200)
    assert cache.get("key") == 200
    assert len(cache) == 1


def test_lru_cache_clear():
    """Test clearing all cached items."""
    cache = LRUCache[str, str](max_size=5)

    cache.set("a", "alpha")
    cache.set("b", "beta")
    cache.set("c", "gamma")

    assert len(cache) == 3
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


def test_lru_cache_min_size_enforced():
    """Test that max_size is clamped to minimum of 1."""
    cache = LRUCache[str, int](max_size=0)
    assert cache.max_size == 1

    cache = LRUCache[str, int](max_size=-5)
    assert cache.max_size == 1

    cache.set("key", 42)
    assert cache.get("key") == 42


def test_lru_cache_get_nonexistent_returns_none():
    """Test that getting a nonexistent key returns None."""
    cache = LRUCache[str, str](max_size=5)
    assert cache.get("nonexistent") is None


def test_lru_cache_generic_types():
    """Test LRU cache with different generic types."""
    # String keys, dict values
    dict_cache = LRUCache[str, dict](max_size=2)
    dict_cache.set("config", {"timeout": 30})
    assert dict_cache.get("config") == {"timeout": 30}

    # Int keys, list values
    list_cache = LRUCache[int, list](max_size=2)
    list_cache.set(1, [1, 2, 3])
    assert list_cache.get(1) == [1, 2, 3]


def test_lru_cache_eviction_order_fifo():
    """Test that eviction follows FIFO order for LRU items."""
    cache = LRUCache[str, int](max_size=3)

    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    cache.set("d", 4)  # Evicts "a"

    assert cache.get("a") is None
    assert len(cache) == 3

    cache.set("e", 5)  # Evicts "b"
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.get("d") == 4
    assert cache.get("e") == 5


def test_lru_cache_multiple_evictions():
    """Test multiple items are evicted if size grows too large."""
    cache = LRUCache[str, int](max_size=2)

    # Fill cache
    cache.set("a", 1)
    cache.set("b", 2)

    # Change max_size and add more items
    # Note: max_size is set at init and shouldn't change,
    # but this tests the eviction loop works correctly
    cache.set("c", 3)
    cache.set("d", 4)

    assert len(cache) == 2
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.get("d") == 4
