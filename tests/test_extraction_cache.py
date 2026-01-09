"""Tests for extraction_cache module."""

from __future__ import annotations

import asyncio

import pytest

from article_extractor.extraction_cache import ExtractionCache
from article_extractor.types import ExtractionOptions


class TestExtractionCache:
    """Tests for ExtractionCache class."""

    def test_initialization(self):
        cache = ExtractionCache(max_size=50)
        assert cache.max_size == 50
        assert cache.size() == 0

    def test_default_max_size(self):
        cache = ExtractionCache()
        assert cache.max_size == 100

    @pytest.mark.asyncio
    async def test_lookup_returns_none_when_empty(self):
        cache = ExtractionCache()
        options = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )
        result = await cache.lookup("https://example.com", options)
        assert result is None

    @pytest.mark.asyncio
    async def test_store_and_lookup(self):
        cache = ExtractionCache()
        options = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )
        response = {
            "url": "https://example.com",
            "title": "Test Article",
            "content": "<p>Test content</p>",
            "word_count": 50,
        }

        await cache.store("https://example.com", options, response)
        cached = await cache.lookup("https://example.com", options)

        assert cached == response
        assert cache.size() == 1

    @pytest.mark.asyncio
    async def test_different_options_create_different_keys(self):
        cache = ExtractionCache()
        url = "https://example.com"

        options1 = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )
        options2 = ExtractionOptions(
            min_word_count=200,  # Different
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        response1 = {"title": "Response 1"}
        response2 = {"title": "Response 2"}

        await cache.store(url, options1, response1)
        await cache.store(url, options2, response2)

        assert await cache.lookup(url, options1) == response1
        assert await cache.lookup(url, options2) == response2
        assert cache.size() == 2

    @pytest.mark.asyncio
    async def test_different_urls_create_different_keys(self):
        cache = ExtractionCache()
        options = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        response1 = {"title": "Article 1"}
        response2 = {"title": "Article 2"}

        await cache.store("https://example.com/page1", options, response1)
        await cache.store("https://example.com/page2", options, response2)

        assert await cache.lookup("https://example.com/page1", options) == response1
        assert await cache.lookup("https://example.com/page2", options) == response2
        assert cache.size() == 2

    @pytest.mark.asyncio
    async def test_clear_removes_all_entries(self):
        cache = ExtractionCache()
        options = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        await cache.store("https://example.com/1", options, {"title": "1"})
        await cache.store("https://example.com/2", options, {"title": "2"})
        assert cache.size() == 2

        await cache.clear()
        assert cache.size() == 0
        assert await cache.lookup("https://example.com/1", options) is None
        assert await cache.lookup("https://example.com/2", options) is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        cache = ExtractionCache(max_size=2)
        options = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        await cache.store("https://example.com/1", options, {"title": "1"})
        await cache.store("https://example.com/2", options, {"title": "2"})
        await cache.store("https://example.com/3", options, {"title": "3"})

        assert cache.size() == 2
        assert await cache.lookup("https://example.com/1", options) is None
        assert await cache.lookup("https://example.com/2", options) == {"title": "2"}
        assert await cache.lookup("https://example.com/3", options) == {"title": "3"}

    @pytest.mark.asyncio
    async def test_concurrent_access_is_safe(self):
        cache = ExtractionCache()
        options = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        async def store_task(idx: int):
            await cache.store(
                f"https://example.com/{idx}", options, {"title": f"Article {idx}"}
            )

        async def lookup_task(idx: int):
            return await cache.lookup(f"https://example.com/{idx}", options)

        # Store concurrently
        await asyncio.gather(*[store_task(i) for i in range(10)])
        assert cache.size() == 10

        # Lookup concurrently
        results = await asyncio.gather(*[lookup_task(i) for i in range(10)])
        assert all(results[i] == {"title": f"Article {i}"} for i in range(10)), (
            "All lookups should succeed"
        )

    @pytest.mark.asyncio
    async def test_cache_key_includes_all_options(self):
        cache = ExtractionCache()
        url = "https://example.com"

        # Test each option variation creates a different key
        base = ExtractionOptions(
            min_word_count=100,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        variations = [
            ExtractionOptions(
                min_word_count=200,  # Different
                min_char_threshold=500,
                include_images=True,
                include_code_blocks=True,
                safe_markdown=True,
            ),
            ExtractionOptions(
                min_word_count=100,
                min_char_threshold=1000,  # Different
                include_images=True,
                include_code_blocks=True,
                safe_markdown=True,
            ),
            ExtractionOptions(
                min_word_count=100,
                min_char_threshold=500,
                include_images=False,  # Different
                include_code_blocks=True,
                safe_markdown=True,
            ),
            ExtractionOptions(
                min_word_count=100,
                min_char_threshold=500,
                include_images=True,
                include_code_blocks=False,  # Different
                safe_markdown=True,
            ),
            ExtractionOptions(
                min_word_count=100,
                min_char_threshold=500,
                include_images=True,
                include_code_blocks=True,
                safe_markdown=False,  # Different
            ),
        ]

        await cache.store(url, base, {"id": "base"})
        for i, opts in enumerate(variations):
            await cache.store(url, opts, {"id": f"variant-{i}"})

        # Each should be independently cached
        assert await cache.lookup(url, base) == {"id": "base"}
        for i, opts in enumerate(variations):
            assert await cache.lookup(url, opts) == {"id": f"variant-{i}"}

        assert cache.size() == 6
