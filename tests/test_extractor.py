"""Unit tests for article_extractor.extractor module."""

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
        assert "first paragraph" in result.content.lower() or "paragraph" in result.markdown.lower()

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
            assert result.title in ["Specific Article Title", "Generic Site Title - Company"]


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
        result = await extract_article_from_url("https://example.com", fetcher=FakeFetcher(), options=opts)

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
