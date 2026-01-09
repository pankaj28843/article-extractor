"""Tests for title extraction module."""

import pytest
from justhtml import JustHTML


@pytest.mark.unit
class TestExtractTitle:
    def test_extracts_og_title(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head>
            <meta property="og:title" content="OG Title">
            <title>Page Title</title>
        </head>
        <body><h1>H1 Title</h1></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "OG Title"

    def test_falls_back_to_h1(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head><title>Page Title</title></head>
        <body><h1>H1 Title</h1></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "H1 Title"

    def test_falls_back_to_title_tag(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head><title>Page Title</title></head>
        <body><p>Content</p></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "Page Title"

    def test_cleans_title_tag_suffix(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head><title>Article Title - Site Name</title></head>
        <body><p>Content</p></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "Article Title"

    def test_keeps_title_without_suffix(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head><title>Simple Title</title></head>
        <body><p>Content</p></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "Simple Title"

    def test_falls_back_to_url(self):
        from article_extractor.title_extractor import extract_title

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html)

        assert extract_title(doc, "https://example.com/my-article") == "My Article"

    def test_url_with_hyphens(self):
        from article_extractor.title_extractor import extract_title

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html)

        assert (
            extract_title(doc, "https://example.com/multi-word-title")
            == "Multi Word Title"
        )

    def test_url_with_underscores(self):
        from article_extractor.title_extractor import extract_title

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html)

        assert (
            extract_title(doc, "https://example.com/under_score_title")
            == "Under Score Title"
        )

    def test_final_fallback_untitled(self):
        from article_extractor.title_extractor import extract_title

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html)

        assert extract_title(doc, "") == "Untitled"

    def test_empty_og_title_falls_back(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head>
            <meta property="og:title" content="">
            <title>Page Title</title>
        </head>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "Page Title"

    def test_empty_h1_falls_back(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head><title>Page Title</title></head>
        <body><h1>   </h1></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc) == "Page Title"

    def test_empty_title_tag_falls_back(self):
        from article_extractor.title_extractor import extract_title

        html = """
        <html>
        <head><title>   </title></head>
        <body><p>Content</p></body>
        </html>
        """
        doc = JustHTML(html)

        assert extract_title(doc, "https://example.com/article") == "Article"

    def test_url_root_path_falls_back_to_untitled(self):
        from article_extractor.title_extractor import extract_title

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html)

        assert extract_title(doc, "https://example.com/") == "Untitled"

    def test_url_no_path_falls_back_to_untitled(self):
        from article_extractor.title_extractor import extract_title

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html)

        assert extract_title(doc, "https://example.com") == "Untitled"


@pytest.mark.unit
class TestTitleFromUrl:
    def test_extracts_last_path_segment(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("https://example.com/blog/my-post") == "My Post"

    def test_handles_trailing_slash(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("https://example.com/blog/my-post/") == "My Post"

    def test_replaces_hyphens(self):
        from article_extractor.title_extractor import _title_from_url

        assert (
            _title_from_url("https://example.com/multi-word-title")
            == "Multi Word Title"
        )

    def test_replaces_underscores(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("https://example.com/under_score") == "Under Score"

    def test_title_case_conversion(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("https://example.com/lowercase") == "Lowercase"

    def test_empty_url_returns_none(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("") is None

    def test_root_path_returns_none(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("https://example.com/") is None

    def test_no_path_returns_none(self):
        from article_extractor.title_extractor import _title_from_url

        assert _title_from_url("https://example.com") is None

    def test_complex_path(self):
        from article_extractor.title_extractor import _title_from_url

        assert (
            _title_from_url("https://example.com/category/sub/article-name")
            == "Article Name"
        )
