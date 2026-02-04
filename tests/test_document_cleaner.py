"""Tests for document cleaning module."""

import pytest
from justhtml import JustHTML


@pytest.mark.unit
class TestCleanDocument:
    def test_removes_scripts(self):
        from article_extractor.document_cleaner import clean_document

        html = "<html><head><script>alert('test')</script></head><body><p>Content</p></body></html>"
        doc = JustHTML(html, safe=False)

        strip_selector = "script"
        role_selector = ""

        clean_document(doc, strip_selector, role_selector)

        assert len(doc.query("script")) == 0
        assert len(doc.query("p")) == 1

    def test_removes_styles(self):
        from article_extractor.document_cleaner import clean_document

        html = "<html><head><style>.test{}</style></head><body><p>Content</p></body></html>"
        doc = JustHTML(html, safe=False)

        strip_selector = "style"
        role_selector = ""

        clean_document(doc, strip_selector, role_selector)

        assert len(doc.query("style")) == 0
        assert len(doc.query("p")) == 1

    def test_removes_multiple_tags(self):
        from article_extractor.document_cleaner import clean_document

        html = """
        <html>
        <head>
            <script>alert('test')</script>
            <style>.test{}</style>
        </head>
        <body>
            <nav>Navigation</nav>
            <article><p>Content</p></article>
            <footer>Footer</footer>
        </body>
        </html>
        """
        doc = JustHTML(html, safe=False)

        strip_selector = "script, style, nav, footer"
        role_selector = ""

        clean_document(doc, strip_selector, role_selector)

        assert len(doc.query("script")) == 0
        assert len(doc.query("style")) == 0
        assert len(doc.query("nav")) == 0
        assert len(doc.query("footer")) == 0
        assert len(doc.query("p")) == 1

    def test_removes_role_elements(self):
        from article_extractor.document_cleaner import clean_document

        html = """
        <div>
            <div role="navigation">Nav</div>
            <div role="dialog">Dialog</div>
            <p>Content</p>
        </div>
        """
        doc = JustHTML(html, safe=False)

        strip_selector = ""
        role_selector = '[role="navigation"], [role="dialog"]'

        clean_document(doc, strip_selector, role_selector)

        navs = doc.query('[role="navigation"]')
        dialogs = doc.query('[role="dialog"]')

        assert len(navs) == 0
        assert len(dialogs) == 0
        assert len(doc.query("p")) == 1

    def test_combined_selectors(self):
        from article_extractor.document_cleaner import clean_document

        html = """
        <html>
        <head><script>test</script></head>
        <body>
            <div role="navigation">Nav</div>
            <article><p>Content</p></article>
        </body>
        </html>
        """
        doc = JustHTML(html, safe=False)

        strip_selector = "script"
        role_selector = '[role="navigation"]'

        clean_document(doc, strip_selector, role_selector)

        assert len(doc.query("script")) == 0
        assert len(doc.query('[role="navigation"]')) == 0
        assert len(doc.query("p")) == 1

    def test_returns_same_document(self):
        from article_extractor.document_cleaner import clean_document

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html, safe=False)

        result = clean_document(doc, "", "")

        assert result is doc

    def test_handles_empty_selectors(self):
        from article_extractor.document_cleaner import clean_document

        html = "<html><body><p>Content</p></body></html>"
        doc = JustHTML(html, safe=False)

        clean_document(doc, "", "")

        # Should not crash, content preserved
        assert len(doc.query("p")) == 1

    def test_preserves_content_elements(self):
        from article_extractor.document_cleaner import clean_document

        html = """
        <html>
        <body>
            <script>bad</script>
            <article>
                <h1>Title</h1>
                <p>Paragraph 1</p>
                <p>Paragraph 2</p>
                <img src="pic.png">
            </article>
        </body>
        </html>
        """
        doc = JustHTML(html, safe=False)

        strip_selector = "script"
        role_selector = ""

        clean_document(doc, strip_selector, role_selector)

        assert len(doc.query("script")) == 0
        assert len(doc.query("h1")) == 1
        assert len(doc.query("p")) == 2
        assert len(doc.query("img")) == 1


@pytest.mark.unit
class TestRemoveNodesBySelector:
    def test_removes_matching_nodes(self):
        from article_extractor.document_cleaner import _remove_nodes_by_selector

        html = "<div><script>test</script><p>Content</p></div>"
        doc = JustHTML(html, safe=False)

        _remove_nodes_by_selector(doc, "script")

        assert len(doc.query("script")) == 0
        assert len(doc.query("p")) == 1

    def test_skips_parentless_nodes(self):
        from article_extractor.document_cleaner import _remove_nodes_by_selector

        class _Node:
            parent = None

        class _Doc:
            def query(self, selector):
                return [_Node()]

        # Should not raise even with parentless node
        _remove_nodes_by_selector(_Doc(), "script")

    def test_removes_multiple_nodes(self):
        from article_extractor.document_cleaner import _remove_nodes_by_selector

        html = "<div><script>1</script><script>2</script><p>Content</p></div>"
        doc = JustHTML(html, safe=False)

        _remove_nodes_by_selector(doc, "script")

        assert len(doc.query("script")) == 0
        assert len(doc.query("p")) == 1

    def test_handles_nested_nodes(self):
        from article_extractor.document_cleaner import _remove_nodes_by_selector

        html = """
        <div>
            <nav>
                <ul>
                    <li>Item</li>
                </ul>
            </nav>
            <p>Content</p>
        </div>
        """
        doc = JustHTML(html, safe=False)

        _remove_nodes_by_selector(doc, "nav")

        assert len(doc.query("nav")) == 0
        assert len(doc.query("ul")) == 0  # Removed with parent
        assert len(doc.query("p")) == 1

    def test_empty_selector_does_nothing(self):
        from article_extractor.document_cleaner import _remove_nodes_by_selector

        html = "<div><p>Content</p></div>"
        doc = JustHTML(html, safe=False)

        _remove_nodes_by_selector(doc, "")

        assert len(doc.query("p")) == 1

    def test_complex_selector(self):
        from article_extractor.document_cleaner import _remove_nodes_by_selector

        html = """
        <div>
            <div class="ads">Ad</div>
            <div class="content">Content</div>
        </div>
        """
        doc = JustHTML(html, safe=False)

        _remove_nodes_by_selector(doc, ".ads")

        assert len(doc.query(".ads")) == 0
        assert len(doc.query(".content")) == 1


@pytest.mark.unit
class TestFormPreservation:
    """Tests for form tag preservation (ASP.NET WebForms compatibility)."""

    def test_form_not_in_strip_tags(self):
        """Verify form is not in STRIP_TAGS constant."""
        from article_extractor.constants import STRIP_TAGS

        assert "form" not in STRIP_TAGS

    def test_aspnet_webforms_content_preserved(self):
        """Test that content inside ASP.NET WebForms wrapper is preserved."""
        from article_extractor.constants import STRIP_TAGS, UNLIKELY_ROLES
        from article_extractor.document_cleaner import clean_document

        html = """
        <html>
        <body id="root">
            <form id="aspnetForm" method="post" action="page.aspx">
                <div id="main" role="main">
                    <article>
                        <h1>Article Title</h1>
                        <p>This is the main article content.</p>
                    </article>
                </div>
            </form>
        </body>
        </html>
        """
        doc = JustHTML(html, safe=False)

        strip_selector = ", ".join(STRIP_TAGS)
        role_selector = ", ".join(f'[role="{role}"]' for role in UNLIKELY_ROLES)

        clean_document(doc, strip_selector, role_selector)

        # Form and its contents should be preserved
        assert len(doc.query("form")) == 1
        assert len(doc.query("article")) == 1
        assert len(doc.query("h1")) == 1
        assert len(doc.query("p")) == 1

    def test_extraction_with_aspnet_form_wrapper(self):
        """Integration test: full extraction with ASP.NET WebForms structure."""
        from article_extractor import extract_article

        html = """
        <html>
        <body id="root">
            <form id="aspnetForm" method="post" action="page.aspx">
                <div id="main" role="main">
                    <article>
                        <h1>Article Title</h1>
                        <p>This is the main article content with enough words to pass validation.</p>
                        <p>Additional paragraph with more content to ensure proper extraction.</p>
                    </article>
                </div>
            </form>
        </body>
        </html>
        """
        result = extract_article(html, "https://example.com/page.aspx")

        assert result.success
        assert "Article Title" in result.markdown
        assert "main article content" in result.markdown

    def test_small_forms_in_content_converted_to_text(self):
        """Test that small forms within content are converted to text, not markup.

        Forms like search boxes or newsletter signups within article content
        are preserved but converted to plain text during markdown extraction,
        which is acceptable behavior.
        """
        from article_extractor import extract_article

        html = """
        <html>
        <body>
            <article>
                <h1>Main Article</h1>
                <p>Article content with substantial text.</p>
                <form action="/search" method="get">
                    <input type="text" name="q" placeholder="Search">
                    <button type="submit">Search</button>
                </form>
                <p>More content after the form.</p>
            </article>
        </body>
        </html>
        """
        result = extract_article(html)

        assert result.success
        # Form elements are converted to text (button text appears)
        # but form markup/inputs are stripped in markdown
        assert "Main Article" in result.markdown
        assert "Article content" in result.markdown
        assert "<form" not in result.markdown
        assert "<input" not in result.markdown
