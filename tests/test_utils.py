"""Unit tests for article_extractor.utils module."""

import pytest

from article_extractor.utils import (
    extract_excerpt,
    get_word_count,
    normalize_whitespace,
)


@pytest.mark.unit
class TestGetWordCount:
    """Test get_word_count function."""

    def test_single_word(self):
        """Single word should return 1."""
        assert get_word_count("hello") == 1

    def test_multiple_words(self):
        """Multiple words should be counted correctly."""
        assert get_word_count("hello world foo bar") == 4

    def test_extra_whitespace(self):
        """Extra whitespace should be handled."""
        assert get_word_count("hello   world") == 2
        assert get_word_count("  hello world  ") == 2

    def test_empty_string(self):
        """Empty string should return 0."""
        assert get_word_count("") == 0
        assert get_word_count("   ") == 0

    def test_newlines_and_tabs(self):
        """Newlines and tabs should be handled as whitespace."""
        assert get_word_count("hello\nworld\tfoo") == 3


@pytest.mark.unit
class TestNormalizeWhitespace:
    """Test normalize_whitespace function."""

    def test_single_spaces_unchanged(self):
        """Text with single spaces should be unchanged."""
        text = "hello world"
        assert normalize_whitespace(text) == text

    def test_multiple_spaces_collapsed(self):
        """Multiple spaces should collapse to single."""
        assert normalize_whitespace("hello   world") == "hello world"

    def test_newlines_collapsed(self):
        """Newlines should collapse to single space."""
        assert normalize_whitespace("hello\nworld") == "hello world"

    def test_tabs_collapsed(self):
        """Tabs should collapse to single space."""
        assert normalize_whitespace("hello\tworld") == "hello world"

    def test_mixed_whitespace(self):
        """Mixed whitespace should normalize."""
        assert normalize_whitespace("hello  \n\t  world") == "hello world"

    def test_leading_trailing_stripped(self):
        """Leading and trailing whitespace should be stripped."""
        assert normalize_whitespace("  hello world  ") == "hello world"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert normalize_whitespace("") == ""


@pytest.mark.unit
class TestExtractExcerpt:
    """Test extract_excerpt function."""

    def test_short_text_unchanged(self):
        """Text shorter than max should be unchanged."""
        text = "This is a short excerpt."
        assert extract_excerpt(text, max_length=100) == text

    def test_long_text_truncated(self):
        """Long text should be truncated with ellipsis."""
        text = "This is a longer piece of text that exceeds the maximum length."
        result = extract_excerpt(text, max_length=20)
        assert len(result) <= 23  # 20 + "..."
        assert result.endswith("...")

    def test_truncates_at_word_boundary(self):
        """Truncation should prefer word boundaries."""
        text = "This is a test sentence for word boundary truncation."
        result = extract_excerpt(text, max_length=25)
        # Should not cut in middle of a word
        assert "..." in result

    def test_empty_string(self):
        """Empty string should return empty."""
        assert extract_excerpt("", max_length=100) == ""

    def test_default_max_length(self):
        """Default max length should be 200."""
        text = "x" * 250
        result = extract_excerpt(text)
        assert len(result) <= 203  # 200 + "..."

    def test_preserves_first_sentence_if_possible(self):
        """Should try to preserve complete first sentence."""
        text = "First sentence. Second sentence that makes it long."
        result = extract_excerpt(text, max_length=50)
        assert "First" in result
