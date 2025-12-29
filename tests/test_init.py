"""Unit tests for article_extractor.__init__ module.

Tests lazy imports and public API exports.
"""

import pytest


@pytest.mark.unit
class TestPublicExports:
    """Test public API exports from article_extractor."""

    def test_extract_article_exported(self):
        """extract_article should be directly importable."""
        from article_extractor import extract_article

        assert callable(extract_article)

    def test_extract_article_from_url_exported(self):
        """extract_article_from_url should be directly importable."""
        from article_extractor import extract_article_from_url

        assert callable(extract_article_from_url)

    def test_article_extractor_class_exported(self):
        """ArticleExtractor class should be directly importable."""
        from article_extractor import ArticleExtractor

        assert ArticleExtractor is not None

    def test_article_result_exported(self):
        """ArticleResult should be directly importable."""
        from article_extractor import ArticleResult

        assert ArticleResult is not None

    def test_extraction_options_exported(self):
        """ExtractionOptions should be directly importable."""
        from article_extractor import ExtractionOptions

        assert ExtractionOptions is not None

    def test_scored_candidate_exported(self):
        """ScoredCandidate should be directly importable."""
        from article_extractor import ScoredCandidate

        assert ScoredCandidate is not None


@pytest.mark.unit
class TestLazyImports:
    """Test lazy imports for optional fetchers."""

    def test_playwright_fetcher_lazy_import(self):
        """PlaywrightFetcher should be lazy-importable."""
        from article_extractor import PlaywrightFetcher

        assert PlaywrightFetcher is not None
        assert PlaywrightFetcher.__name__ == "PlaywrightFetcher"

    def test_httpx_fetcher_lazy_import(self):
        """HttpxFetcher should be lazy-importable."""
        from article_extractor import HttpxFetcher

        assert HttpxFetcher is not None
        assert HttpxFetcher.__name__ == "HttpxFetcher"

    def test_get_default_fetcher_lazy_import(self):
        """get_default_fetcher should be lazy-importable."""
        from article_extractor import get_default_fetcher

        assert callable(get_default_fetcher)

    def test_fetcher_protocol_lazy_import(self):
        """Fetcher protocol should be lazy-importable."""
        from article_extractor import Fetcher

        assert Fetcher is not None

    def test_invalid_attribute_raises(self):
        """Accessing invalid attribute should raise AttributeError."""
        import article_extractor

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = article_extractor.NonExistentClass


@pytest.mark.unit
class TestAllList:
    """Test __all__ list contains expected exports."""

    def test_all_contains_main_exports(self):
        """__all__ should contain main exports."""
        import article_extractor

        expected = [
            "ArticleExtractor",
            "ArticleResult",
            "ExtractionOptions",
            "ScoredCandidate",
            "extract_article",
            "extract_article_from_url",
            "PlaywrightFetcher",
            "HttpxFetcher",
            "get_default_fetcher",
            "Fetcher",
        ]

        for name in expected:
            assert name in article_extractor.__all__, f"{name} not in __all__"


@pytest.mark.unit
class TestDirectInstantiation:
    """Test that exported classes can be instantiated."""

    def test_article_extractor_instantiable(self):
        """ArticleExtractor should be instantiable."""
        from article_extractor import ArticleExtractor

        extractor = ArticleExtractor()
        assert extractor is not None
        assert hasattr(extractor, "extract")

    def test_article_result_instantiable(self):
        """ArticleResult should be instantiable."""
        from article_extractor import ArticleResult

        result = ArticleResult(
            url="https://example.com",
            title="Test",
            content="<p>Test</p>",
            markdown="Test",
            excerpt="Test",
            word_count=1,
            success=True,
        )
        assert result.url == "https://example.com"
        assert result.success is True

    def test_extraction_options_instantiable(self):
        """ExtractionOptions should be instantiable with defaults."""
        from article_extractor import ExtractionOptions

        opts = ExtractionOptions()
        assert opts.min_word_count == 150
        assert opts.min_char_threshold == 500

    def test_extraction_options_custom_values(self):
        """ExtractionOptions should accept custom values."""
        from article_extractor import ExtractionOptions

        opts = ExtractionOptions(min_word_count=50, min_char_threshold=200)
        assert opts.min_word_count == 50
        assert opts.min_char_threshold == 200

    def test_playwright_fetcher_instantiable(self):
        """PlaywrightFetcher should be instantiable."""
        from article_extractor import PlaywrightFetcher

        fetcher = PlaywrightFetcher()
        assert fetcher is not None
        assert fetcher.headless is True

    def test_httpx_fetcher_instantiable(self):
        """HttpxFetcher should be instantiable."""
        from article_extractor import HttpxFetcher

        fetcher = HttpxFetcher()
        assert fetcher is not None
        assert fetcher.timeout == 30.0
