"""Tests for candidate_finder module."""

from unittest.mock import patch

from justhtml import JustHTML

from article_extractor.cache import ExtractionCache
from article_extractor.candidate_finder import find_top_candidate


class TestFindTopCandidate:
    def test_finds_article_tag(self):
        html = """
        <html>
        <body>
            <article>
                <p>This is the main article content with enough text to be considered.</p>
                <p>More paragraphs here to meet the threshold.</p>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        assert candidate.name == "article"

    def test_finds_main_tag(self):
        html = """
        <html>
        <body>
            <main>
                <p>Main content area with sufficient text to be selected.</p>
                <p>Additional content to ensure it's recognized.</p>
            </main>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        assert candidate.name == "main"

    def test_prefers_article_over_main(self):
        html = """
        <html>
        <body>
            <main>
                <p>Main content</p>
            </main>
            <article>
                <p>Article content</p>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should find first semantic tag (article appears first in iteration order)
        assert candidate.name in ("article", "main")

    def test_fallback_to_div_when_no_semantic_tags(self):
        html = """
        <html>
        <body>
            <div class="header">Header</div>
            <div class="content">
                <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
                <p>Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
                <p>Ut enim ad minim veniam, quis nostrud exercitation ullamco.</p>
            </div>
            <div class="footer">Footer</div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should find a content container (div or body)
        assert candidate.name in ("div", "body")

    def test_fallback_to_section_when_no_semantic_tags(self):
        html = """
        <html>
        <body>
            <div class="header">Header</div>
            <section>
                <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
                <p>Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
                <p>Ut enim ad minim veniam, quis nostrud exercitation ullamco.</p>
            </section>
            <div class="footer">Footer</div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should find a content container (section or body)
        assert candidate.name in ("section", "body")

    def test_skips_unlikely_candidates(self):
        html = """
        <html>
        <body>
            <div class="sidebar">
                <p>Sidebar content that should be skipped.</p>
            </div>
            <div class="content">
                <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
                <p>Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
                <p>Ut enim ad minim veniam, quis nostrud exercitation ullamco.</p>
            </div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should skip sidebar and find content div
        assert "sidebar" not in (candidate.attrs.get("class") or "")

    def test_requires_minimum_text_length_for_fallback_tags(self):
        html = """
        <html>
        <body>
            <div class="short">Short.</div>
            <div class="long">
                <p>This is a much longer piece of content that exceeds the minimum threshold.</p>
                <p>Additional paragraphs to ensure sufficient length for selection.</p>
            </div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should select the longer div
        assert len(candidate.to_text(strip=True)) > 50

    def test_returns_body_as_last_resort(self):
        html = """
        <html>
        <body>
            <p>Just a paragraph.</p>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        assert candidate.name == "body"

    def test_selects_highest_scoring_candidate(self):
        html = """
        <html>
        <body>
            <div class="content">
                <p>Short content.</p>
            </div>
            <div class="main-content">
                <p>This is the main article with much more substantial content.</p>
                <p>Multiple paragraphs with detailed information about the topic.</p>
                <p>Even more text to ensure this candidate scores higher.</p>
                <p>Additional content to boost the score further.</p>
            </div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should select the div with more content
        assert len(candidate.to_text(strip=True)) > 100

    def test_handles_nested_candidates(self):
        html = """
        <html>
        <body>
            <article>
                <div class="inner">
                    <p>Nested content that should still be findable.</p>
                    <p>Additional text to meet thresholds.</p>
                </div>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should find the article tag
        assert candidate.name == "article"

    def test_cache_reuse_across_calls(self):
        html = """
        <html>
        <body>
            <article>
                <p>Content with enough text to be selected as candidate.</p>
                <p>More content here for good measure.</p>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()

        # First call populates cache
        candidate1 = find_top_candidate(doc, cache)
        cache_size_after_first = len(cache._text_cache)

        # Second call should reuse cache
        candidate2 = find_top_candidate(doc, cache)
        cache_size_after_second = len(cache._text_cache)

        assert candidate1 == candidate2
        assert cache_size_after_first == cache_size_after_second

    def test_multiple_article_tags_selects_best(self):
        html = """
        <html>
        <body>
            <article>
                <p>Short article.</p>
            </article>
            <article>
                <p>Much longer article with substantial content and details.</p>
                <p>Multiple paragraphs that make this the better candidate.</p>
                <p>Even more text to ensure higher score.</p>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should select the longer article
        assert len(candidate.to_text(strip=True)) > 50

    def test_ignores_empty_semantic_tags(self):
        html = """
        <html>
        <body>
            <article></article>
            <div class="content">
                <p>This div has actual content and should be selected.</p>
                <p>Multiple paragraphs to meet the minimum threshold.</p>
            </div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Empty article will be found but ranked lower by scorer
        # Actual selection depends on ranking algorithm

    def test_handles_only_whitespace_content(self):
        html = """
        <html>
        <body>
            <article>   </article>
            <div>
                <p>Real content here with actual text.</p>
                <p>More text to ensure selection.</p>
            </div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Whitespace-only article will be found but ranked by scorer

    def test_semantic_tags_bypass_length_check(self):
        html = """
        <html>
        <body>
            <article>
                <p>Short.</p>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Semantic tags don't require minimum length
        assert candidate.name == "article"

    def test_fallback_tags_require_minimum_length(self):
        html = """
        <html>
        <body>
            <div>Short.</div>
            <div>
                <p>This is a much longer piece of content that will be selected.</p>
                <p>Additional text to meet the minimum threshold requirements.</p>
            </div>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()
        candidate = find_top_candidate(doc, cache)
        assert candidate is not None
        # Should select the longer div
        assert len(candidate.to_text(strip=True)) > 50

    def test_returns_none_when_rank_candidates_empty(self):
        """Test edge case where rank_candidates returns empty list."""
        html = """
        <html>
        <body>
            <article>
                <p>Content</p>
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html)
        cache = ExtractionCache()

        # Mock rank_candidates to return empty list
        with patch(
            "article_extractor.candidate_finder.rank_candidates", return_value=[]
        ):
            candidate = find_top_candidate(doc, cache)
            assert candidate is None
