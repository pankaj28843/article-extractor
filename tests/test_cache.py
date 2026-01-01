"""Tests for cache module."""

import pytest
from justhtml import JustHTML

from article_extractor.cache import ExtractionCache


@pytest.mark.unit
class TestExtractionCache:
    """Test ExtractionCache class."""

    def test_init(self):
        """Cache should initialize empty."""
        cache = ExtractionCache()
        assert cache._text_cache == {}
        assert cache._link_density_cache == {}

    def test_get_node_text(self):
        """Should cache and return node text."""
        cache = ExtractionCache()
        doc = JustHTML("<p>Test content</p>")
        nodes = doc.query("p")

        text = cache.get_node_text(nodes[0])
        assert text == "Test content"

        text2 = cache.get_node_text(nodes[0])
        assert text2 == text

    def test_get_text_length(self):
        """Should return text length."""
        cache = ExtractionCache()
        doc = JustHTML("<p>Hello world</p>")
        nodes = doc.query("p")

        length = cache.get_text_length(nodes[0])
        assert length == 11

    def test_get_link_density(self):
        """Should calculate and cache link density."""
        cache = ExtractionCache()
        doc = JustHTML('<div>Text <a href="#">link</a> more</div>')
        nodes = doc.query("div")

        density = cache.get_link_density(nodes[0])
        assert 0.0 < density < 1.0

        density2 = cache.get_link_density(nodes[0])
        assert density2 == density

    def test_get_link_density_empty(self):
        """Empty node should have 0 density."""
        cache = ExtractionCache()
        doc = JustHTML("<div></div>")
        nodes = doc.query("div")

        density = cache.get_link_density(nodes[0])
        assert density == 0.0

    def test_clear(self):
        """Clear should empty caches."""
        cache = ExtractionCache()
        doc = JustHTML("<p>Content</p>")
        nodes = doc.query("p")

        cache.get_node_text(nodes[0])
        cache.get_link_density(nodes[0])

        cache.clear()

        assert cache._text_cache == {}
        assert cache._link_density_cache == {}
