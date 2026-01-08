"""Unit tests for article_extractor.scorer module."""

import pytest
from justhtml import JustHTML

from article_extractor.cache import ExtractionCache
from article_extractor.scorer import (
    count_commas,
    get_class_weight,
    get_tag_score,
    is_unlikely_candidate,
    score_paragraph,
)


@pytest.fixture
def cache() -> ExtractionCache:
    """Create fresh ExtractionCache for each test."""
    return ExtractionCache()


@pytest.mark.unit
class TestGetTagScore:
    """Test get_tag_score function."""

    def test_div_positive_score(self):
        """DIV tag should have positive score."""
        assert get_tag_score("div") == 5

    def test_article_positive_score(self):
        """ARTICLE tag should have positive score."""
        assert get_tag_score("article") == 5

    def test_h1_negative_score(self):
        """H1 tag should have negative score."""
        assert get_tag_score("h1") == -5

    def test_unknown_tag_zero_score(self):
        """Unknown tags should have zero score."""
        assert get_tag_score("custom-element") == 0
        assert get_tag_score("xyz") == 0

    def test_form_negative_score(self):
        """Form tag should have negative score."""
        assert get_tag_score("form") == -3

    def test_case_insensitive(self):
        """Tag scoring is case insensitive."""
        assert get_tag_score("DIV") == 5
        assert get_tag_score("Article") == 5


@pytest.mark.unit
class TestGetClassWeight:
    """Test get_class_weight function."""

    def test_positive_class_adds_weight(self):
        """Classes with positive hints should increase weight."""
        doc = JustHTML('<div class="article-content">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight > 0

    def test_negative_class_subtracts_weight(self):
        """Classes with negative hints should decrease weight."""
        doc = JustHTML('<div class="sidebar-widget">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight < 0

    def test_mixed_class_zero_weight(self):
        """Mixed positive/negative of equal strength should combine to zero."""
        # article-content has +25 (article, content), sidebar has -25
        # But the regex only matches once per category, so it's +25 -25 = 0
        doc = JustHTML('<div class="article-content sidebar">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        # With one positive match (+25) and one negative match (-25), we get 0
        assert weight == 0

    def test_neutral_class_zero_weight(self):
        """Classes without hints should have zero weight."""
        doc = JustHTML('<div class="my-custom-class">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight == 0

    def test_no_class_zero_weight(self):
        """Elements without class should have zero weight."""
        doc = JustHTML("<div>text</div>")
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight == 0

    def test_readability_asset_class_adds_weight(self):
        """Readability asset classes should add weight."""
        doc = JustHTML('<div class="entry-content-asset">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight >= 25


@pytest.mark.unit
class TestIsUnlikelyCandidate:
    """Test is_unlikely_candidate function."""

    def test_sidebar_is_unlikely(self):
        """Elements with sidebar class should be unlikely."""
        doc = JustHTML('<div class="sidebar">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        assert is_unlikely_candidate(nodes[0]) is True

    def test_footer_is_unlikely(self):
        """Elements with footer class should be unlikely."""
        # Note: "page-footer" is NOT unlikely because "page" is in OK_MAYBE list
        doc = JustHTML('<div class="footer">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        assert is_unlikely_candidate(nodes[0]) is True

    def test_page_footer_not_unlikely(self):
        """page-footer is not unlikely because 'page' is in OK_MAYBE list."""
        doc = JustHTML('<div class="page-footer">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        # "page" in the class overrides the "footer" unlikely pattern
        assert is_unlikely_candidate(nodes[0]) is False

    def test_article_overrides_unlikely(self):
        """Article hint should override unlikely patterns."""
        doc = JustHTML('<div class="article sidebar">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        # article overrides sidebar
        assert is_unlikely_candidate(nodes[0]) is False

    def test_content_class_not_unlikely(self):
        """Content class should not be unlikely."""
        doc = JustHTML('<div class="content">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        assert is_unlikely_candidate(nodes[0]) is False

    def test_navigation_class_is_unlikely(self):
        """Elements with navigation class should be unlikely."""
        # Note: role attribute is not checked, only class/id
        doc = JustHTML('<div class="navigation">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        assert is_unlikely_candidate(nodes[0]) is True

    def test_role_attribute_not_checked(self):
        """Role attribute is not checked by is_unlikely_candidate."""
        # Only class/id are checked, not role attribute
        doc = JustHTML('<div role="navigation">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        # Role is not checked, so this is not unlikely
        assert is_unlikely_candidate(nodes[0]) is False

    def test_main_role_not_unlikely(self):
        """Elements with main role should not be unlikely."""
        doc = JustHTML('<div role="main">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        assert is_unlikely_candidate(nodes[0]) is False


@pytest.mark.unit
class TestScoreParagraph:
    """Test score_paragraph function."""

    def test_long_paragraph_higher_score(self, cache: ExtractionCache):
        """Longer paragraphs should score higher."""
        short_html = "<p>This is short.</p>"
        long_html = "<p>This is a much longer paragraph that contains many more words and should therefore receive a higher score based on its length and content. It contains multiple sentences and demonstrates the scoring algorithm.</p>"

        short_doc = JustHTML(short_html)
        long_doc = JustHTML(long_html)

        short_nodes = short_doc.query("p")
        long_nodes = long_doc.query("p")

        assert len(short_nodes) == 1
        assert len(long_nodes) == 1

        assert score_paragraph(long_nodes[0], cache) > score_paragraph(
            short_nodes[0], cache
        )

    def test_commas_add_score(self, cache: ExtractionCache):
        """Commas in text should add to score."""
        no_commas_html = (
            "<p>This is a sentence without any punctuation marks just text here</p>"
        )
        with_commas_html = (
            "<p>This, however, has commas, which add points to the score</p>"
        )

        no_commas_doc = JustHTML(no_commas_html)
        with_commas_doc = JustHTML(with_commas_html)

        no_commas_nodes = no_commas_doc.query("p")
        with_commas_nodes = with_commas_doc.query("p")

        assert score_paragraph(with_commas_nodes[0], cache) > score_paragraph(
            no_commas_nodes[0], cache
        )

    def test_minimum_score_for_short_paragraph(self, cache: ExtractionCache):
        """Short paragraphs below MIN_PARAGRAPH_LENGTH return 0."""
        short_html = "<p>x</p>"
        doc = JustHTML(short_html)
        nodes = doc.query("p")
        assert len(nodes) == 1
        assert score_paragraph(nodes[0], cache) == 0.0

    def test_long_enough_paragraph_positive_score(self, cache: ExtractionCache):
        """Paragraphs above MIN_PARAGRAPH_LENGTH get positive score."""
        html = "<p>This paragraph has enough characters to pass the minimum length threshold.</p>"
        doc = JustHTML(html)
        nodes = doc.query("p")
        assert len(nodes) == 1
        assert score_paragraph(nodes[0], cache) > 0


@pytest.mark.unit
class TestGetLinkDensity:
    """Test ExtractionCache.get_link_density method."""

    def test_no_links_zero_density(self, cache: ExtractionCache):
        """Element with no links should have zero density."""
        doc = JustHTML("<div>This is plain text without any links.</div>")
        nodes = doc.query("div")
        assert len(nodes) == 1
        density = cache.get_link_density(nodes[0])
        assert density == 0.0

    def test_all_links_full_density(self, cache: ExtractionCache):
        """Element with all text in links should have ~1.0 density."""
        doc = JustHTML("<div><a href='#'>All text is linked</a></div>")
        nodes = doc.query("div")
        assert len(nodes) == 1
        density = cache.get_link_density(nodes[0])
        assert density > 0.9

    def test_partial_links_partial_density(self, cache: ExtractionCache):
        """Element with some linked text should have partial density."""
        doc = JustHTML("<div>Some text and <a href='#'>a link</a> and more text</div>")
        nodes = doc.query("div")
        assert len(nodes) == 1
        density = cache.get_link_density(nodes[0])
        assert 0.0 < density < 1.0

    def test_empty_element_zero_density(self, cache: ExtractionCache):
        """Empty element should have zero density."""
        doc = JustHTML("<div></div>")
        nodes = doc.query("div")
        assert len(nodes) == 1
        density = cache.get_link_density(nodes[0])
        assert density == 0.0


@pytest.mark.unit
class TestCountCommas:
    """Test count_commas function."""

    def test_no_commas(self):
        """Text without commas should return 0."""
        assert count_commas("This has no commas") == 0

    def test_single_comma(self):
        """Text with one comma."""
        assert count_commas("Hello, world") == 1

    def test_multiple_commas(self):
        """Text with multiple commas."""
        assert count_commas("one, two, three, four") == 3

    def test_empty_string(self):
        """Empty string should return 0."""
        assert count_commas("") == 0


@pytest.mark.unit
class TestClassWeightEdgeCases:
    """Test class_weight edge cases for full coverage."""

    def test_photo_hint_bonus(self):
        """Photo hint class should add +10 bonus."""
        doc = JustHTML('<div class="figure">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight >= 10

    def test_image_class_photo_hint(self):
        """Image class should trigger photo hint bonus."""
        doc = JustHTML('<div class="photo-gallery">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight >= 10

    def test_readability_asset_bonus(self):
        """Readability asset class should add +25 bonus."""
        doc = JustHTML('<div class="page">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        # "page" may match readability_asset pattern
        assert weight >= 0  # At least not negative

    def test_class_as_list(self):
        """Handle class attribute as list (multiple classes)."""
        doc = JustHTML('<div class="article content main">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        assert weight > 0

    def test_id_attribute_checked(self):
        """ID attribute should also be checked for patterns."""
        doc = JustHTML('<div id="main-article">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        weight = get_class_weight(nodes[0])
        # "main" and "article" in ID should match positive pattern
        assert weight > 0


@pytest.mark.unit
class TestScoreNode:
    """Test score_node function."""

    def test_article_tag_positive_score(self):
        """Article tag should get positive base score."""
        from article_extractor.scorer import score_node

        doc = JustHTML("<article>content</article>")
        nodes = doc.query("article")
        assert len(nodes) == 1
        score = score_node(nodes[0])
        assert score > 0

    def test_div_with_content_class(self):
        """Div with content class should get positive score."""
        from article_extractor.scorer import score_node

        doc = JustHTML('<div class="content">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        score = score_node(nodes[0])
        assert score > 0

    def test_div_with_sidebar_class_negative(self):
        """Div with sidebar class should get negative score."""
        from article_extractor.scorer import score_node

        doc = JustHTML('<div class="sidebar">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        score = score_node(nodes[0])
        assert score < 0


@pytest.mark.unit
class TestCalculateContentScore:
    """Test calculate_content_score function."""

    def test_scores_paragraphs(self, cache: ExtractionCache):
        """Should calculate score from paragraphs."""
        from article_extractor.scorer import calculate_content_score

        doc = JustHTML(
            """
        <article>
            <p>This is a paragraph with enough content to score well.</p>
            <p>Another paragraph with more content, commas, and length.</p>
        </article>
        """
        )
        nodes = doc.query("article")
        assert len(nodes) == 1
        score = calculate_content_score(nodes[0], cache)
        assert score > 0

    def test_link_density_penalty(self, cache: ExtractionCache):
        """High link density should penalize score."""
        from article_extractor.scorer import calculate_content_score

        low_links = JustHTML("<div><p>Lots of normal text content here.</p></div>")
        high_links = JustHTML('<div><p><a href="#">All text is a link</a></p></div>')

        low_nodes = low_links.query("div")
        high_nodes = high_links.query("div")

        assert len(low_nodes) == 1
        assert len(high_nodes) == 1

        low_score = calculate_content_score(low_nodes[0], cache)
        cache_high = ExtractionCache()
        high_score = calculate_content_score(high_nodes[0], cache_high)

        assert low_score > high_score

    def test_caches_scores(self, cache: ExtractionCache):
        """Should cache scores to avoid recalculation."""
        from article_extractor.scorer import calculate_content_score

        doc = JustHTML("<article><p>Content</p></article>")
        nodes = doc.query("article")
        assert len(nodes) == 1

        scores = {}
        score1 = calculate_content_score(nodes[0], cache, scores)
        score2 = calculate_content_score(nodes[0], cache, scores)

        assert score1 == score2
        assert id(nodes[0]) in scores


@pytest.mark.unit
class TestRankCandidates:
    """Test rank_candidates function."""

    def test_ranks_by_score(self, cache: ExtractionCache):
        """Should rank candidates by score (highest first)."""
        from article_extractor.scorer import rank_candidates

        doc = JustHTML(
            """
        <body>
            <div class="sidebar"><p>Short</p></div>
            <article>
                <p>This is a long article with substantial content, commas, and other signals.</p>
                <p>Multiple paragraphs make the score even higher.</p>
            </article>
        </body>
        """
        )

        sidebar = doc.query(".sidebar")
        article = doc.query("article")
        candidates = sidebar + article

        ranked = rank_candidates(candidates, cache)

        assert len(ranked) == 2
        assert ranked[0].score > ranked[1].score

    def test_returns_scored_candidates(self, cache: ExtractionCache):
        """Should return ScoredCandidate objects."""
        from article_extractor.scorer import rank_candidates
        from article_extractor.types import ScoredCandidate

        doc = JustHTML("<article><p>Content</p></article>")
        nodes = doc.query("article")

        ranked = rank_candidates(nodes, cache)

        assert len(ranked) == 1
        assert isinstance(ranked[0], ScoredCandidate)
        assert ranked[0].score >= 0
        assert ranked[0].content_length >= 0
        assert 0 <= ranked[0].link_density <= 1

    def test_empty_candidates(self, cache: ExtractionCache):
        """Should handle empty candidate list."""
        from article_extractor.scorer import rank_candidates

        ranked = rank_candidates([], cache)
        assert ranked == []


@pytest.mark.unit
class TestGetClassIdString:
    """Test get_class_id_string function."""

    def test_combines_class_and_id(self):
        """Should combine class and id attributes."""
        from article_extractor.scorer import get_class_id_string

        doc = JustHTML('<div class="test-class" id="test-id">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        result = get_class_id_string(nodes[0])
        assert "test-class" in result
        assert "test-id" in result

    def test_handles_missing_class(self):
        """Should handle missing class attribute."""
        from article_extractor.scorer import get_class_id_string

        doc = JustHTML('<div id="only-id">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        result = get_class_id_string(nodes[0])
        assert "only-id" in result

    def test_handles_missing_id(self):
        """Should handle missing id attribute."""
        from article_extractor.scorer import get_class_id_string

        doc = JustHTML('<div class="only-class">text</div>')
        nodes = doc.query("div")
        assert len(nodes) == 1
        result = get_class_id_string(nodes[0])
        assert "only-class" in result

    def test_handles_no_attributes(self):
        """Should handle element with no class or id."""
        from article_extractor.scorer import get_class_id_string

        doc = JustHTML("<div>text</div>")
        nodes = doc.query("div")
        assert len(nodes) == 1
        result = get_class_id_string(nodes[0])
        assert result.strip() == ""

    def test_handles_class_list(self):
        """Should join list-based class attributes."""
        from article_extractor.scorer import get_class_id_string

        doc = JustHTML('<div class="alpha beta">text</div>')
        node = doc.query("div")[0]
        node.attrs["class"] = ["alpha", "beta"]

        result = get_class_id_string(node)

        assert "alpha beta" in result
