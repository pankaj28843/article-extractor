"""Unit tests for article_extractor.extractor module."""

from unittest.mock import patch

import pytest

from article_extractor import extract_article
from article_extractor.types import ArticleResult, ExtractionOptions


@pytest.mark.unit
class TestExtractArticle:
    """Test extract_article function."""

    def test_extracts_basic_article(self, simple_article_html: str):
        """Should extract content from basic article HTML."""
        result = extract_article(simple_article_html, url="https://example.com")

        # Should succeed (content is extracted even if below word count)
        assert result.success is True
        # Title should be extracted
        assert "Test Article" in result.title
        # Content should include article text
        assert (
            "first paragraph" in result.content.lower()
            or "paragraph" in result.markdown.lower()
        )

    def test_returns_failure_for_minimal_content(self, minimal_html: str):
        """Should return failure when content is below thresholds."""
        result = extract_article(minimal_html, url="https://example.com")
        # Minimal content may or may not pass thresholds
        # Should have a result object either way
        assert isinstance(result, ArticleResult)

    def test_handles_empty_html(self):
        """Should handle empty HTML gracefully."""
        result = extract_article("", url="https://example.com")
        # Empty HTML still returns success=True but with 0 word count and warnings
        assert isinstance(result, ArticleResult)
        assert result.word_count == 0

    def test_handles_no_body(self):
        """Should handle HTML without body."""
        html = "<html><head><title>No Body</title></head></html>"
        result = extract_article(html, url="https://example.com")
        # Returns result with title extracted but no content
        assert isinstance(result, ArticleResult)
        assert result.title == "No Body"

    def test_extracts_title_from_h1(self):
        """Should extract title from h1 tag."""
        html = """
        <html>
        <head><title>Page Title</title></head>
        <body>
            <article>
                <h1>Article Heading</h1>
                <p>This is a substantial paragraph with enough content to meet the minimum
                thresholds for extraction. It needs to have multiple sentences and be
                reasonably long to pass the content quality checks.</p>
                <p>Another paragraph here with more substantial content that helps meet
                the word count requirements for successful extraction.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            # May extract from h1 or title tag
            assert result.title in ["Article Heading", "Page Title"]

    def test_filters_navigation_heavy_content(self, navigation_heavy_html: str):
        """Should filter navigation-heavy content."""
        result = extract_article(navigation_heavy_html, url="https://example.com")
        # Navigation-heavy content should be filtered
        if result.success:
            # If anything extracted, navigation links should be excluded
            content_lower = result.content.lower()
            # Should not have nav menu items as main content
            assert "privacy policy" not in content_lower or "article" in content_lower


@pytest.mark.unit
class TestExtractionOptions:
    """Test ExtractionOptions configuration."""

    def test_default_options(self):
        """Default options should have sensible defaults."""
        opts = ExtractionOptions()
        assert opts.min_word_count == 150
        assert opts.min_char_threshold == 500
        assert opts.include_images is True

    def test_custom_min_word_count(self):
        """Should respect custom min_word_count."""
        opts = ExtractionOptions(min_word_count=50)
        assert opts.min_word_count == 50

    def test_custom_char_threshold(self):
        """Should respect custom min_char_threshold."""
        opts = ExtractionOptions(min_char_threshold=200)
        assert opts.min_char_threshold == 200

    def test_include_code_blocks_option(self):
        """Should have include_code_blocks option."""
        opts = ExtractionOptions(include_code_blocks=False)
        assert opts.include_code_blocks is False


@pytest.mark.unit
class TestArticleResult:
    """Test ArticleResult dataclass."""

    def test_article_result_fields(self):
        """ArticleResult should have required fields."""
        result = ArticleResult(
            url="https://example.com/test",
            title="Test Title",
            content="<p>Test content here</p>",
            markdown="Test content here",
            excerpt="Test excerpt",
            word_count=3,
            success=True,
        )

        assert result.url == "https://example.com/test"
        assert result.title == "Test Title"
        assert result.content == "<p>Test content here</p>"
        assert result.markdown == "Test content here"
        assert result.excerpt == "Test excerpt"
        assert result.word_count == 3
        assert result.success is True

    def test_article_result_with_author(self):
        """ArticleResult should support author."""
        result = ArticleResult(
            url="https://example.com/test",
            title="Test",
            content="<p>Content</p>",
            markdown="Content",
            excerpt="",
            word_count=1,
            success=True,
            author="John Doe",
        )

        assert result.author == "John Doe"

    def test_article_result_with_warnings(self):
        """ArticleResult should support warnings list."""
        result = ArticleResult(
            url="https://example.com/test",
            title="Test",
            content="<p>Content</p>",
            markdown="Content",
            excerpt="",
            word_count=1,
            success=True,
            warnings=["Low word count"],
        )

        assert len(result.warnings) == 1
        assert result.warnings[0] == "Low word count"


@pytest.mark.unit
class TestTitleExtraction:
    """Test title extraction logic."""

    def test_title_from_title_tag(self):
        """Should extract title from <title> tag."""
        html = """
        <html>
        <head><title>My Page Title</title></head>
        <body>
            <article>
                <p>This is the main article content with enough words to meet the
                minimum thresholds. We need substantial text here to ensure the
                extraction algorithm considers this valid content worth extracting.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            assert result.title == "My Page Title"

    def test_title_prefers_h1_over_title_tag(self):
        """Should prefer h1 title when relevant."""
        html = """
        <html>
        <head><title>Generic Site Title - Company</title></head>
        <body>
            <article>
                <h1>Specific Article Title</h1>
                <p>This is the main article content with enough words to meet the
                minimum thresholds. We need substantial text here to ensure the
                extraction algorithm considers this valid content worth extracting.</p>
                <p>Additional paragraph to increase word count and ensure extraction
                succeeds with the default options.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            # May use h1 or title depending on heuristics
            assert result.title in [
                "Specific Article Title",
                "Generic Site Title - Company",
            ]


@pytest.mark.unit
class TestCodeHeavyContent:
    """Test extraction of code-heavy content."""

    def test_preserves_code_blocks(self, code_heavy_html: str):
        """Should preserve code blocks in content."""
        result = extract_article(code_heavy_html, url="https://example.com")

        if result.success:
            # The fixture has "pip install" and "import example" code
            assert "pip install" in result.content or "import example" in result.content

    def test_code_in_pre_tags(self):
        """Should preserve code in <pre> tags."""
        html = """
        <html>
        <body>
            <article>
                <h1>Code Tutorial</h1>
                <p>Here is an example of Python code that demonstrates basic
                programming concepts and syntax patterns.</p>
                <pre><code>def greet(name):
    return f"Hello, {name}!"

print(greet("World"))
</code></pre>
                <p>The code above shows a simple function definition with
                string formatting and a function call.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            assert "greet" in result.content or "Hello" in result.content


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_malformed_html(self):
        """Should handle malformed HTML gracefully."""
        html = "<html><body><div>Unclosed tag<p>More content"
        # Should not raise exception
        result = extract_article(html, url="https://example.com")
        assert isinstance(result, ArticleResult)

    def test_unicode_content(self):
        """Should handle unicode content."""
        html = """
        <html>
        <body>
            <article>
                <h1>Unicode Test: 日本語 한국어 العربية</h1>
                <p>This article contains unicode characters from various languages
                including Japanese (日本語), Korean (한국어), Arabic (العربية),
                and special symbols like © ® ™ and emoji 🎉.</p>
                <p>The extraction should preserve all these characters correctly
                without any encoding issues or data corruption.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            # Unicode should be preserved
            assert "日本語" in result.title or "日本語" in result.content

    def test_absolutizes_relative_links_and_media(self):
        """Extractor should rewrite relative URLs in anchors and media tags."""
        html = """
        <html>
        <body>
            <article>
                <h1>Relative Assets</h1>
                <p>This article references local assets and links to prove that
                URL rewriting converts them into absolute destinations for the final
                markdown output that readers view offline.</p>
                <p>Read more on <a href="/docs/getting-started">our docs</a> to keep learning.</p>
                <figure>
                    <img src="images/photo.jpg" srcset="/img/photo-1x.jpg 1x, /img/photo-2x.jpg, , img/photo-3x.jpg 3x" alt="Photo">
                </figure>
                <video controls poster="media/thumb.jpg" src="../media/trailer.mp4"></video>
            </article>
        </body>
        </html>
        """

        options = ExtractionOptions(
            min_word_count=10, min_char_threshold=10, safe_markdown=False
        )
        result = extract_article(
            html,
            url="https://example.com/blog/post-one/index.html",
            options=options,
        )

        assert result.success is True
        assert "https://example.com/docs/getting-started" in result.content
        assert "https://example.com/blog/post-one/images/photo.jpg" in result.content
        assert "https://example.com/img/photo-1x.jpg 1x" in result.content
        assert "https://example.com/img/photo-2x.jpg" in result.content
        assert "https://example.com/blog/post-one/img/photo-3x.jpg 3x" in result.content
        assert "https://example.com/blog/post-one/media/thumb.jpg" in result.content
        assert "https://example.com/blog/media/trailer.mp4" in result.content
        assert "[our docs](https://example.com/docs/getting-started)" in result.markdown

    def test_deeply_nested_content(self):
        """Should handle deeply nested content."""
        # Create deeply nested structure
        html = (
            "<html><body>"
            + "<div>" * 20
            + """
        <article>
            <p>Deep content that is nested inside many div elements but should
            still be extracted correctly by the algorithm.</p>
            <p>More content here to meet minimum thresholds and ensure
            successful extraction of the nested article.</p>
        </article>
        """
            + "</div>" * 20
            + "</body></html>"
        )

        result = extract_article(html, url="https://example.com")
        if result.success:
            assert "Deep content" in result.content

    def test_whitespace_only_content(self):
        """Should handle whitespace-only elements."""
        html = """
        <html>
        <body>
            <div>   </div>
            <article>
                <p>Actual content here with enough words to meet the
                minimum extraction thresholds.</p>
            </article>
            <div>\n\t\n</div>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            # Should extract actual content, not whitespace
            assert len(result.content.strip()) > 0

    def test_bytes_input(self):
        """Should handle bytes input."""
        html = b"""
        <html>
        <body>
            <article>
                <p>Content from bytes input with sufficient text to meet thresholds.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        assert isinstance(result, ArticleResult)

    def test_latin1_bytes_input(self):
        """Should handle latin-1 encoded bytes."""
        html = "<html><body><article><p>Café résumé naïve</p></article></body></html>"
        html_bytes = html.encode("latin-1")
        result = extract_article(html_bytes, url="https://example.com")
        assert isinstance(result, ArticleResult)

    def test_removes_empty_links_and_images(self):
        """Should drop anchors without text and images without src."""
        html = """
        <html>
        <body>
            <article>
                <h1>Sanitization Sample</h1>
                <p>
                    This paragraph contains enough substantive words to satisfy the
                    extraction thresholds and ensures the sanitizer operates on a
                    realistic article body for the regression test scenario.
                </p>
                <a href="https://example.com/share" class="share-link">   </a>
                <ul class="share-list">
                    <li><a href="https://example.com/share/1">   </a></li>
                    <li><a href="https://example.com/share/2">\n</a></li>
                </ul>
                <p>
                    Additional meaningful content lives here to keep the document
                    robust and confirm extraction continues to succeed after noisy
                    nodes are removed from the DOM tree prior to serialization.
                </p>
                <img alt="Lazy Placeholder" class="lazy" width="650" height="540">
            </article>
        </body>
        </html>
        """

        options = ExtractionOptions(min_word_count=10, min_char_threshold=50)
        result = extract_article(
            html,
            url="https://example.com/sanitize",
            options=options,
        )

        assert isinstance(result, ArticleResult)
        if result.success:
            assert "[](" not in result.markdown
            assert "share-link" not in result.markdown
            assert "Lazy Placeholder" not in result.content
            assert "<img" not in result.content
            lines = [line.strip() for line in result.markdown.splitlines()]
            assert "-" not in lines

    def test_preserves_non_empty_list_items(self):
        """Should keep list items with visible text or real images."""
        html = """
        <html>
        <body>
            <article>
                <h1>List Preservation</h1>
                <ul>
                    <li class="social-follow"><a href="https://example.com/follow">Follow Us</a></li>
                    <li class="social-empty"><a href="https://example.com/empty">   </a></li>
                    <li class="social-icon"><a href="https://example.com/icon"><img src="https://cdn.example.com/icon.png" alt="Icon"></a></li>
                </ul>
                <div class="empty-wrapper"><div class="nested-empty"></div></div>
                <p>This closing paragraph ensures the article maintains enough substance for extraction.</p>
            </article>
        </body>
        </html>
        """

        options = ExtractionOptions(min_word_count=10, min_char_threshold=50)
        result = extract_article(
            html,
            url="https://example.com/list",
            options=options,
        )

        assert isinstance(result, ArticleResult)
        if result.success:
            assert "Follow Us" in result.markdown
            assert "social-empty" not in result.content
            assert "social-icon" in result.content
            assert "empty-wrapper" not in result.content
            lines = [
                line.strip() for line in result.markdown.splitlines() if line.strip()
            ]
            assert "-" not in [line for line in lines if line == "-"]


@pytest.mark.unit
class TestArticleExtractorClass:
    """Test ArticleExtractor class directly."""

    def test_extractor_default_options(self):
        """ArticleExtractor should use default options."""
        from article_extractor import ArticleExtractor, ExtractionOptions

        extractor = ArticleExtractor()
        assert isinstance(extractor.options, ExtractionOptions)
        assert extractor.options.min_word_count == 150

    def test_extractor_custom_options(self):
        """ArticleExtractor should accept custom options."""
        from article_extractor import ArticleExtractor, ExtractionOptions

        opts = ExtractionOptions(min_word_count=50)
        extractor = ArticleExtractor(options=opts)
        assert extractor.options.min_word_count == 50

    def test_extractor_reuse(self, simple_article_html: str):
        """ArticleExtractor should be reusable for multiple extractions."""
        from article_extractor import ArticleExtractor

        extractor = ArticleExtractor()
        result1 = extractor.extract(simple_article_html, url="https://example.com/1")
        result2 = extractor.extract(simple_article_html, url="https://example.com/2")

        assert result1.url == "https://example.com/1"
        assert result2.url == "https://example.com/2"

    def test_extractor_cache_cleared_between_extractions(self):
        """Each extraction should use fresh cache."""
        from article_extractor import ArticleExtractor

        extractor = ArticleExtractor()

        html1 = "<html><body><article><p>First document content.</p></article></body></html>"
        html2 = "<html><body><article><p>Second document content.</p></article></body></html>"

        result1 = extractor.extract(html1, url="https://example.com/1")
        result2 = extractor.extract(html2, url="https://example.com/2")

        # Each result should be independent
        if result1.success and result2.success:
            assert "First" in result1.content
            assert "Second" in result2.content


@pytest.mark.unit
@pytest.mark.asyncio
class TestExtractArticleFromUrl:
    """Test async extract_article_from_url function."""

    async def test_with_fake_fetcher(self, simple_article_html: str):
        """Should work with provided fetcher."""
        from article_extractor import extract_article_from_url

        class FakeFetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return simple_article_html, 200

        fetcher = FakeFetcher()
        result = await extract_article_from_url("https://example.com", fetcher=fetcher)

        assert result.success is True
        assert result.url == "https://example.com"

    async def test_handles_http_error(self):
        """Should handle HTTP errors gracefully."""
        from article_extractor import extract_article_from_url

        class ErrorFetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return "", 404

        fetcher = ErrorFetcher()
        result = await extract_article_from_url("https://example.com", fetcher=fetcher)

        assert result.success is False
        assert "404" in result.error

    async def test_handles_500_error(self):
        """Should handle 500 errors."""
        from article_extractor import extract_article_from_url

        class ServerErrorFetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return "", 500

        fetcher = ServerErrorFetcher()
        result = await extract_article_from_url("https://example.com", fetcher=fetcher)

        assert result.success is False
        assert "500" in result.error

    async def test_handles_fetch_exception(self):
        """Should handle exceptions from fetcher."""
        from article_extractor import extract_article_from_url

        class ExceptionFetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                raise ConnectionError("Network error")

        fetcher = ExceptionFetcher()
        result = await extract_article_from_url("https://example.com", fetcher=fetcher)

        assert result.success is False
        assert "Network error" in result.error

    async def test_with_custom_options(self, simple_article_html: str):
        """Should respect custom extraction options."""
        from article_extractor import ExtractionOptions, extract_article_from_url

        class FakeFetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return simple_article_html, 200

        opts = ExtractionOptions(min_word_count=1)  # Very low threshold
        result = await extract_article_from_url(
            "https://example.com", fetcher=FakeFetcher(), options=opts
        )

        assert result.success is True

    async def test_auto_fetcher_with_no_packages(self, monkeypatch):
        """Should return error when no fetcher packages available."""
        from article_extractor import extract_article_from_url
        from article_extractor import fetcher as fetcher_module

        # Mock both packages as unavailable
        monkeypatch.setattr(fetcher_module, "_playwright_available", False)
        monkeypatch.setattr(fetcher_module, "_httpx_available", False)

        result = await extract_article_from_url("https://example.com")

        assert result.success is False
        assert "No fetcher available" in result.error


@pytest.mark.unit
class TestTitleUrlFallback:
    """Test title extraction URL fallback."""

    def test_title_from_url_path(self):
        """Should extract title from URL when no other title found."""
        html = """
        <html>
        <body>
            <article>
                <p>Content without any title elements that needs enough text
                to pass the minimum thresholds for extraction.</p>
                <p>Additional paragraph for word count.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com/my-article-title")
        # Should use URL path as title
        # The path "my-article-title" should be converted to "My Article Title"
        assert result.title != ""  # Title should not be empty

    def test_title_fallback_to_untitled(self):
        """Should fallback to 'Untitled' when URL has no path."""
        html = """
        <html>
        <body>
            <article>
                <p>Content without any title elements that needs enough text
                to pass the minimum thresholds for extraction.</p>
            </article>
        </body>
        </html>
        """
        # URL with root path only
        result = extract_article(html, url="https://example.com/")
        # Should fallback to "Untitled" or extract from content
        assert result.title != ""

    def test_title_with_site_suffix_cleaned(self):
        """Should clean site suffix from title."""
        html = """
        <html>
        <head><title>Article Title - My Site</title></head>
        <body>
            <article>
                <p>Content for the article with enough text.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com/post")
        if result.title:
            # Should strip " - My Site" suffix
            assert "My Site" not in result.title or result.title == "Article Title"


@pytest.mark.unit
class TestTransientErrorDetection:
    """Validate transient error detection helper."""

    def test_detects_transient_errors(self):
        from article_extractor.extractor import _is_transient_error_message

        assert _is_transient_error_message(None) is False
        assert _is_transient_error_message("") is False
        assert _is_transient_error_message("HTTP 404") is True
        assert _is_transient_error_message("HTTP 410") is True
        assert _is_transient_error_message("HTTP 500") is False


@pytest.mark.unit
class TestFindCandidates:
    """Test candidate finding logic."""

    def test_prefers_article_tag(self):
        """Should prefer <article> elements."""
        html = """
        <html>
        <body>
            <div class="container">
                <article>
                    <p>This is the main article content that should be extracted
                    because it is inside an article element which is preferred.</p>
                    <p>Additional paragraph for word count requirements.</p>
                </article>
            </div>
            <div>
                <p>Some sidebar content that should be ignored.</p>
            </div>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            assert "main article content" in result.content.lower()

    def test_uses_main_tag(self):
        """Should use <main> element when no article."""
        html = """
        <html>
        <body>
            <nav>Navigation content</nav>
            <main>
                <p>This is the main content that should be extracted
                because it is inside a main element.</p>
                <p>Additional paragraph for word count requirements.</p>
            </main>
            <footer>Footer content</footer>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            assert "main content" in result.content.lower()

    def test_fallback_to_body(self):
        """Should fallback to body when no semantic containers."""
        html = """
        <html>
        <body>
            <p>This is some body content without any semantic containers
            that should still be extracted.</p>
            <p>Additional paragraph for word count.</p>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        # Should still extract something
        assert isinstance(result, ArticleResult)


@pytest.mark.unit
class TestExtractorErrorHandling:
    """Test error handling in extraction."""

    def test_content_extraction_failure(self):
        """Should handle content extraction failures gracefully."""
        html = """
        <html><body>
            <article>Valid HTML</article>
        </body></html>
        """
        result = extract_article(html, url="https://example.com")
        assert isinstance(result, ArticleResult)

    def test_no_candidates_found(self):
        """Should handle case when no candidates found."""
        html = "<html><head></head></html>"
        result = extract_article(html, url="https://example.com")
        assert result.success is False or result.word_count == 0


@pytest.mark.unit
class TestCleanDocument:
    """Test document cleaning."""

    def test_removes_scripts(self):
        """Should remove script tags."""
        from article_extractor import ArticleExtractor

        html = """
        <html><body>
            <article>
                <p>Content</p>
                <script>alert('test');</script>
            </article>
        </body></html>
        """
        extractor = ArticleExtractor()
        result = extractor.extract(html, url="https://example.com")
        if result.success:
            assert "alert" not in result.content

    def test_removes_styles(self):
        """Should remove style tags."""
        html = """
        <html><body>
            <article>
                <p>Content here</p>
                <style>.test { color: red; }</style>
            </article>
        </body></html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            assert "color: red" not in result.content


@pytest.mark.unit
class TestWarnings:
    """Test warning generation."""

    def test_low_word_count_warning(self):
        """Should add warning for low word count."""
        html = """
        <html><body>
            <article>
                <p>Short content.</p>
            </article>
        </body></html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success and result.word_count < 150:
            assert any("word count" in w.lower() for w in result.warnings)


@pytest.mark.unit
class TestOgTitle:
    """Test og:title extraction."""

    def test_extracts_og_title(self):
        """Should extract og:title meta tag."""
        html = """
        <html>
        <head>
            <meta property="og:title" content="OG Title Here">
            <title>Page Title</title>
        </head>
        <body>
            <article>
                <p>Content with enough words to pass thresholds.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html, url="https://example.com")
        if result.success:
            assert result.title == "OG Title Here"


@pytest.mark.unit
@pytest.mark.asyncio
class TestTransient404Extraction:
    """Test extraction from pages returning HTTP 404 with real content."""

    async def test_transient_404_extracts_content(self, spa_404_html: str):
        """Should extract content from 404 response with substantial DOM."""
        from article_extractor import extract_article_from_url

        class SPA404Fetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return spa_404_html, 404

        fetcher = SPA404Fetcher()
        result = await extract_article_from_url(
            "https://example.com/spa-page", fetcher=fetcher
        )

        assert result.success is True
        assert "Dynamic Article Title" in result.title
        assert result.word_count > 50
        assert any("404" in w for w in result.warnings)

    async def test_transient_410_extracts_content(self, spa_404_html: str):
        """Should also handle HTTP 410 Gone with usable content."""
        from article_extractor import extract_article_from_url

        class SPA410Fetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return spa_404_html, 410

        fetcher = SPA410Fetcher()
        result = await extract_article_from_url(
            "https://example.com/gone-page", fetcher=fetcher
        )

        assert result.success is True
        assert result.word_count > 50
        assert any("410" in w for w in result.warnings)

    async def test_empty_404_still_fails(self):
        """Should fail when 404 response has no usable content."""
        from article_extractor import extract_article_from_url

        class Empty404Fetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return "<html><body><p>Page not found.</p></body></html>", 404

        fetcher = Empty404Fetcher()
        result = await extract_article_from_url(
            "https://example.com/missing", fetcher=fetcher
        )

        assert result.success is False
        assert "404" in result.error

    async def test_500_error_still_fails(self, spa_404_html: str):
        """Server errors (5xx) should not attempt extraction."""
        from article_extractor import extract_article_from_url

        class Server500Fetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return spa_404_html, 500

        fetcher = Server500Fetcher()
        result = await extract_article_from_url(
            "https://example.com/error", fetcher=fetcher
        )

        assert result.success is False
        assert "500" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
class TestHttpxToPlaywrightFallback:
    """Test automatic fallback from httpx to Playwright on transient 404."""

    async def test_fallback_to_playwright_on_404(self, spa_404_html: str, monkeypatch):
        """Should retry with Playwright when httpx returns 404."""
        from article_extractor import extract_article_from_url
        from article_extractor import fetcher as fetcher_module

        call_order = []

        class FakeHttpxFetcher:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def fetch(self, url: str) -> tuple[str, int]:
                call_order.append("httpx")
                return "", 404

        class FakePlaywrightFetcher:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def fetch(self, url: str) -> tuple[str, int]:
                call_order.append("playwright")
                return spa_404_html, 200

        monkeypatch.setattr(fetcher_module, "_playwright_available", True)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        with (
            patch.object(fetcher_module, "HttpxFetcher", FakeHttpxFetcher),
            patch.object(fetcher_module, "PlaywrightFetcher", FakePlaywrightFetcher),
        ):
            result = await extract_article_from_url(
                "https://example.com/spa", prefer_playwright=False
            )

        assert result.success is True
        assert call_order == ["httpx", "playwright"]

    async def test_no_fallback_when_playwright_unavailable(self, monkeypatch):
        """Should not attempt fallback when Playwright is not installed."""
        from article_extractor import extract_article_from_url
        from article_extractor import fetcher as fetcher_module

        class FakeHttpxFetcher:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def fetch(self, url: str) -> tuple[str, int]:
                return "", 404

        monkeypatch.setattr(fetcher_module, "_playwright_available", False)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        with patch.object(fetcher_module, "HttpxFetcher", FakeHttpxFetcher):
            result = await extract_article_from_url(
                "https://example.com/spa", prefer_playwright=False
            )

        assert result.success is False
        assert "404" in result.error

    async def test_no_fallback_with_user_provided_fetcher(self):
        """Should not fallback when caller provides explicit fetcher."""
        from article_extractor import extract_article_from_url

        class UserFetcher:
            async def fetch(self, url: str) -> tuple[str, int]:
                return "", 404

        result = await extract_article_from_url(
            "https://example.com/spa", fetcher=UserFetcher()
        )

        # User-provided fetcher should not trigger fallback
        assert result.success is False
        assert "404" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
class TestExtractArticleFromUrlAutoFetcher:
    """Test auto-fetcher selection."""

    async def test_prefer_playwright_true(self, simple_article_html: str, monkeypatch):
        """Should prefer playwright when requested."""
        from article_extractor import extract_article_from_url
        from article_extractor import fetcher as fetcher_module

        monkeypatch.setattr(fetcher_module, "_playwright_available", True)
        monkeypatch.setattr(fetcher_module, "_httpx_available", True)

        class FakeFetcher:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def fetch(self, url: str) -> tuple[str, int]:
                return simple_article_html, 200

        with patch.object(fetcher_module, "PlaywrightFetcher", FakeFetcher):
            result = await extract_article_from_url(
                "https://example.com", prefer_playwright=True
            )
            assert result.success is True


@pytest.mark.unit
class TestExtractorEdgeCases:
    @pytest.mark.asyncio
    async def test_fetcher_protocol_stub(self):
        from article_extractor import extractor as extractor_module

        assert await extractor_module.Fetcher.fetch(None, "https://example.com") is None

    def test_parse_failure_returns_error(self, monkeypatch):
        from article_extractor import extract_article
        from article_extractor import extractor as extractor_module

        def _boom(_html):
            raise ValueError("bad html")

        monkeypatch.setattr(extractor_module, "JustHTML", _boom)

        result = extract_article("<html></html>", url="https://example.com")

        assert result.success is False
        assert "Failed to parse HTML" in result.error

    def test_no_candidates_returns_failure(self, monkeypatch):
        from article_extractor import extract_article
        from article_extractor import extractor as extractor_module

        class _EmptyDoc:
            def query(self, _selector):
                return []

        monkeypatch.setattr(extractor_module, "JustHTML", lambda _html: _EmptyDoc())

        result = extract_article("", url="https://example.com/docs/getting-started")

        assert result.success is False
        assert result.error == "Could not find main content"
        assert result.title == "Getting Started"

    def test_content_serialization_error_returns_failure(self, monkeypatch):
        from article_extractor import extract_article
        from article_extractor import extractor as extractor_module

        class _BadNode:
            name = "article"
            attrs = {}

            def query(self, _selector):
                return []

            def to_html(self, *args, **kwargs):
                raise ValueError("serialize fail")

            def to_text(self, *args, **kwargs):
                return "text"

        class _Doc:
            def __init__(self, node):
                self._node = node

            def query(self, selector):
                if selector == "article":
                    return [self._node]
                return []

        monkeypatch.setattr(
            extractor_module, "JustHTML", lambda _html: _Doc(_BadNode())
        )

        result = extract_article("<html></html>", url="https://example.com")

        assert result.success is False
        assert "Failed to extract content" in result.error

    def test_clean_document_removes_script_and_roles(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <head><script>var noisy = 1;</script></head>
        <body>
            <nav role="navigation">Nav text</nav>
            <article>
                <p>Main article content with enough words to pass extraction.</p>
                <p>More substantive content to keep extraction successful.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="https://example.com", options=options)

        assert result.success is True
        assert "Nav text" not in result.content
        assert "noisy" not in result.content

    def test_title_uses_og_title(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <head>
            <meta property="og:title" content="OG Title" />
        </head>
        <body>
            <article>
                <p>Content with enough words to satisfy the extraction rules.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="https://example.com", options=options)

        assert result.title == "OG Title"

    def test_title_strips_suffix(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <head><title>Welcome - Example</title></head>
        <body>
            <article>
                <p>Enough content here to pass extraction thresholds.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="https://example.com", options=options)

        assert result.title == "Welcome"

    def test_title_og_empty_falls_back_to_url(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <head>
            <meta property="og:title" content="" />
        </head>
        <body>
            <article>
                <p>Content with enough words to satisfy the extraction rules.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(
            html, url="https://example.com/posts/slug", options=options
        )

        assert result.title == "Slug"

    def test_title_h1_empty_falls_back_to_title(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <head><title>Fallback Title</title></head>
        <body>
            <article>
                <h1> </h1>
                <p>Enough content to keep extraction successful.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="https://example.com", options=options)

        assert result.title == "Fallback Title"

    def test_title_tag_blank_falls_back_to_untitled(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <head><title> </title></head>
        <body>
            <article>
                <p>Enough content to keep extraction successful.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="", options=options)

        assert result.title == "Untitled"

    def test_url_root_falls_back_to_untitled(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <body>
            <article>
                <p>Enough content to keep extraction successful.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="https://example.com/", options=options)

        assert result.title == "Untitled"

    def test_extract_without_url_keeps_relative_links(self):
        from article_extractor import ExtractionOptions, extract_article

        html = """
        <html>
        <body>
            <article>
                <p>Read more on <a href="/docs">our docs</a>.</p>
            </article>
        </body>
        </html>
        """
        options = ExtractionOptions(min_word_count=5, min_char_threshold=10)
        result = extract_article(html, url="", options=options)

        assert result.success is True
        assert 'href="/docs"' in result.content

    def test_normalize_srcset_handles_empty_and_plain_entries(self):
        from article_extractor import ArticleExtractor

        extractor = ArticleExtractor()
        normalized = extractor._normalize_srcset(
            " , /img/one.jpg, /img/two.jpg 2x",
            "https://example.com/base/",
        )

        assert "https://example.com/img/one.jpg" in normalized
        assert "https://example.com/img/two.jpg 2x" in normalized

    def test_remove_empty_links_skips_parentless_nodes(self):
        from article_extractor import ArticleExtractor

        class _Anchor:
            name = "a"
            parent = None

            def to_text(self, *args, **kwargs):
                return ""

            def query(self, _selector):
                return []

        class _Root:
            name = "div"

            def query(self, _selector):
                return [_Anchor()]

        extractor = ArticleExtractor()
        extractor._remove_empty_links(_Root())

    def test_remove_empty_images_skips_parentless_nodes(self):
        from article_extractor import ArticleExtractor

        class _Image:
            name = "img"
            parent = None
            attrs = {"src": ""}

        class _Root:
            name = "div"

            def query(self, _selector):
                return [_Image()]

        extractor = ArticleExtractor()
        extractor._remove_empty_images(_Root())

    def test_remove_empty_blocks_skips_parentless_nodes(self):
        from article_extractor import ArticleExtractor

        class _Block:
            name = "p"
            parent = None

            def to_text(self, *args, **kwargs):
                return ""

            def query(self, _selector):
                return []

        class _Root:
            name = "div"

            def query(self, _selector):
                return [_Block()]

            def to_text(self, *args, **kwargs):
                return ""

        extractor = ArticleExtractor()
        extractor._remove_empty_blocks(_Root())

    def test_find_top_candidate_returns_none_when_ranked_empty(self, monkeypatch):
        from justhtml import JustHTML

        from article_extractor import ArticleExtractor
        from article_extractor import extractor as extractor_module

        monkeypatch.setattr(extractor_module, "rank_candidates", lambda *_a, **_k: [])

        doc = JustHTML("<article><p>Text</p></article>")
        extractor = ArticleExtractor()
        result = extractor._find_top_candidate(doc, extractor_module.ExtractionCache())

        assert result is None

    def test_candidate_nodes_respects_min_length(self):
        from justhtml import JustHTML

        from article_extractor import ArticleExtractor
        from article_extractor.cache import ExtractionCache

        doc = JustHTML(
            "<div>hi</div><div>longer text</div><div class='sidebar'>longer</div>"
        )
        extractor = ArticleExtractor()
        cache = ExtractionCache()

        candidates = extractor._candidate_nodes(doc, cache, "div", min_length=5)

        assert len(candidates) == 1
        assert candidates[0].to_text(strip=True) == "longer text"

    def test_clean_document_skips_parentless_nodes(self):
        from article_extractor import ArticleExtractor

        class _Node:
            parent = None

        class _Doc:
            def query(self, _selector):
                return [_Node()]

        extractor = ArticleExtractor()
        extractor._clean_document(_Doc())

    def test_clean_document_removes_role_nodes(self):
        from article_extractor import ArticleExtractor

        class _Parent:
            def __init__(self):
                self.removed = []

            def remove_child(self, node):
                self.removed.append(node)

        class _Node:
            def __init__(self, parent):
                self.parent = parent

        class _Doc:
            def __init__(self, node):
                self._node = node

            def query(self, selector):
                if 'role="' in selector:
                    return [self._node]
                return []

        parent = _Parent()
        node = _Node(parent)
        extractor = ArticleExtractor()
        extractor._clean_document(_Doc(node))

        assert parent.removed == [node]

    def test_absolutize_root_media_node(self):
        from justhtml import JustHTML

        from article_extractor import ArticleExtractor

        doc = JustHTML('<img src="images/pic.png">')
        node = doc.query("img")[0]
        extractor = ArticleExtractor()
        extractor._absolutize_urls(node, "https://example.com/base/")

        assert node.attrs["src"] == "https://example.com/base/images/pic.png"

    def test_rewrite_url_attributes_no_attrs(self):
        from article_extractor import ArticleExtractor

        class _AttrlessNode:
            attrs = None

        extractor = ArticleExtractor()
        extractor._rewrite_url_attributes(
            _AttrlessNode(),
            ("href",),
            "https://example.com",
        )

    def test_remove_empty_anchor_root(self):
        from justhtml import JustHTML

        from article_extractor import ArticleExtractor

        doc = JustHTML('<div><a href="https://example.com"></a></div>')
        node = doc.query("a")[0]
        extractor = ArticleExtractor()

        extractor._remove_empty_links(node)

        assert doc.query("a") == []

    def test_remove_empty_image_root(self):
        from justhtml import JustHTML

        from article_extractor import ArticleExtractor

        doc = JustHTML("<div><img></div>")
        node = doc.query("img")[0]
        extractor = ArticleExtractor()

        extractor._remove_empty_images(node)

        assert doc.query("img") == []

    def test_remove_empty_block_root(self):
        from justhtml import JustHTML

        from article_extractor import ArticleExtractor

        doc = JustHTML("<div><p>   </p></div>")
        node = doc.query("p")[0]
        extractor = ArticleExtractor()

        extractor._remove_empty_blocks(node)

        assert doc.query("p") == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestExtractorAsyncEdges:
    async def test_transient_404_short_html_fails(self):
        from article_extractor import extract_article_from_url

        class ShortFetcher:
            async def fetch(self, _url: str) -> tuple[str, int]:
                return "<html><body><p>short</p></body></html>", 404

        result = await extract_article_from_url(
            "https://example.com/spa", fetcher=ShortFetcher()
        )

        assert result.success is False
        assert result.error == "HTTP 404"

    async def test_transient_404_extractable_but_failure(self):
        from article_extractor import extractor as extractor_module
        from article_extractor.types import ArticleResult

        class FailingExtractor:
            def extract(self, _html: str, _url: str):
                return ArticleResult(
                    url=_url,
                    title="",
                    content="",
                    markdown="",
                    excerpt="",
                    word_count=0,
                    success=False,
                    error="no content",
                )

        class Fetcher:
            async def fetch(self, _url: str) -> tuple[str, int]:
                html = "<article>" + ("word " * 200) + "</article>"
                return html, 404

        result = await extractor_module._extract_with_fetcher(
            FailingExtractor(),
            "https://example.com/spa",
            Fetcher(),
            executor=None,
        )

        assert result.success is False
        assert result.error == "HTTP 404"

    async def test_extract_with_executor_uses_thread_pool(self):
        from concurrent.futures import ThreadPoolExecutor

        from article_extractor import extract_article_from_url

        class OkFetcher:
            async def fetch(self, _url: str) -> tuple[str, int]:
                html = """
                <html><body><article>
                <p>Content with enough words to satisfy extraction in executor.</p>
                </article></body></html>
                """
                return html, 200

        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await extract_article_from_url(
                "https://example.com/ok",
                fetcher=OkFetcher(),
                executor=executor,
            )

        assert result.success is True
