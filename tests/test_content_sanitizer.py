"""Tests for content sanitization module."""

import pytest
from justhtml import JustHTML


@pytest.mark.unit
class TestSanitizeContent:
    def test_sanitize_removes_empty_links(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><a href="/link"></a><p>Text</p></div>', safe=False)
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("a")) == 0
        assert len(doc.query("p")) == 1

    def test_sanitize_keeps_links_with_text(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><a href="/link">Link text</a></div>', safe=False)
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("a")) == 1

    def test_sanitize_removes_images_without_src(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<div><img><p>Text</p></div>", safe=False)
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("img")) == 0
        assert len(doc.query("p")) == 1

    def test_sanitize_keeps_images_with_src(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><img src="image.png"></div>', safe=False)
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("img")) == 1

    def test_sanitize_removes_empty_paragraphs(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<div><p>   </p><p>Real text</p></div>", safe=False)
        root = doc.query("div")[0]
        sanitize_content(root)

        paragraphs = doc.query("p")
        assert len(paragraphs) == 1
        assert "Real text" in paragraphs[0].to_text()

    def test_sanitize_removes_empty_list_items(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<ul><li></li><li>Item</li></ul>", safe=False)
        root = doc.query("ul")[0]
        sanitize_content(root)

        items = doc.query("li")
        assert len(items) == 1
        assert "Item" in items[0].to_text()

    def test_sanitize_removes_empty_divs(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML(
            "<div><div class='wrapper'></div><div>Content</div></div>", safe=False
        )
        root = doc.query("div")[0]
        sanitize_content(root)

        # Root div still exists, but empty wrapper div is removed
        divs = root.query("div")
        assert len(divs) == 1
        assert "Content" in divs[0].to_text()

    def test_sanitize_keeps_blocks_with_images(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><p><img src="pic.png"></p></div>', safe=False)
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("p")) == 1
        assert len(doc.query("img")) == 1

    def test_sanitize_combined_cleanup(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML(
            """
            <div>
                <a></a>
                <img>
                <p></p>
                <p>Good content</p>
                <a href="/link">Good link</a>
                <img src="good.png">
            </div>
            """,
            safe=False,
        )
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("a")) == 1
        assert len(doc.query("img")) == 1
        assert len(doc.query("p")) == 1


@pytest.mark.unit
class TestRemoveEmptyLinks:
    def test_remove_empty_anchor_root(self):
        from article_extractor.content_sanitizer import _remove_empty_links

        doc = JustHTML('<div><a href="https://example.com"></a></div>', safe=False)
        node = doc.query("a")[0]
        _remove_empty_links(node)

        assert doc.query("a") == []

    def test_remove_empty_links_skips_parentless_nodes(self):
        from article_extractor.content_sanitizer import _remove_empty_links

        class _Anchor:
            name = "a"
            parent = None

            def to_text(self, *args, **kwargs):
                return ""

            def query(self, selector):
                return []

        anchor = _Anchor()
        # Should not raise
        _remove_empty_links(anchor)


@pytest.mark.unit
class TestRemoveEmptyImages:
    def test_remove_empty_image_root(self):
        from article_extractor.content_sanitizer import _remove_empty_images

        doc = JustHTML("<div><img></div>", safe=False)
        node = doc.query("img")[0]
        _remove_empty_images(node)

        assert doc.query("img") == []

    def test_keeps_image_with_valid_src(self):
        from article_extractor.content_sanitizer import _remove_empty_images

        doc = JustHTML('<div><img src="pic.png"></div>', safe=False)
        root = doc.query("div")[0]
        _remove_empty_images(root)

        assert len(doc.query("img")) == 1

    def test_removes_image_with_empty_src(self):
        from article_extractor.content_sanitizer import _remove_empty_images

        doc = JustHTML('<div><img src=""></div>', safe=False)
        root = doc.query("div")[0]
        _remove_empty_images(root)

        assert len(doc.query("img")) == 0


@pytest.mark.unit
class TestRemoveEmptyBlocks:
    def test_remove_empty_block_root(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML("<div><p>   </p></div>", safe=False)
        node = doc.query("p")[0]
        _remove_empty_blocks(node)

        assert doc.query("p") == []

    def test_keeps_blocks_with_text(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML("<div><p>Text</p></div>", safe=False)
        root = doc.query("div")[0]
        _remove_empty_blocks(root)

        assert len(doc.query("p")) == 1

    def test_keeps_blocks_with_images(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML('<div><div><img src="pic.png"></div></div>', safe=False)
        root = doc.query("div")[0]
        _remove_empty_blocks(root)

        # Root div still there, inner div kept (has image)
        assert len(root.query("div")) == 1

    def test_removes_nested_empty_blocks(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML("<div><div><p></p></div><div>Content</div></div>", safe=False)
        root = doc.query("div")[0]
        _remove_empty_blocks(root)

        # Empty paragraph removed, but divs remain (one has content)
        assert len(doc.query("p")) == 0


@pytest.mark.unit
class TestHasValidImageSrc:
    def test_valid_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="pic.png">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_data_url_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML(
            '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==">',
            safe=False,
        )
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_data_url_rejects_non_image(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML(
            '<img src="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">',
            safe=False,
        )
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_absolute_url_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="https://example.com/image.jpg">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_relative_path_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="/images/photo.jpg">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_parent_relative_path_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="../images/photo.jpg">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_protocol_relative_url_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="//cdn.example.com/image.jpg">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_legitimate_images_with_tracking_keywords_accepted(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        # These should NOT be rejected despite containing tracking keywords
        legitimate_images = [
            "my-pixel-art.png",
            "tracking-dashboard.jpg",
            "pixel-perfect-design.svg",
            "beacon-hill-photo.jpg",
            "spacer-component.png",
            "https://example.com/assets/my-pixel.gif",
            # Dimension patterns in legitimate filenames
            "image-1x1-grid.jpg",
            "photo-1x1-ratio.png",
            "section-0x0a.jpg",
            "grid-1x1-layout.svg",
        ]

        for src in legitimate_images:
            doc = JustHTML(f'<img src="{src}">', safe=False)
            node = doc.query("img")[0]
            assert _has_valid_image_src(node) is True, (
                f"Should accept legitimate image: {src}"
            )

    def test_specific_tracking_patterns_rejected(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        # These should be rejected as they match specific tracking patterns
        tracking_images = [
            "/pixel.gif",
            "/1x1.png",
            "https://tracking.example.com/image.jpg",
            "https://analytics.site.com/beacon.gif",
            "https://cdn.example.com/t.gif",
            "https://cdn.example.com/p.png",
            "https://cdn.example.com/x.jpg",
            # Short tracking filenames
            "t.gif",
            "p.png",
            "x.jpg",
        ]

        for src in tracking_images:
            doc = JustHTML(f'<img src="{src}">', safe=False)
            node = doc.query("img")[0]
            assert _has_valid_image_src(node) is False, (
                f"Should reject tracking image: {src}"
            )

    def test_domain_tracking_edge_cases(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        # Test edge cases with tracking keywords in domains
        test_cases = [
            ("https://tracking.example.com/image.jpg", False),  # tracking subdomain
            (
                "https://example.tracking.com/image.jpg",
                True,
            ),  # tracking in middle of domain
            ("//tracking.example.com/image.jpg", False),  # protocol-relative tracking
            ("https://analytics.cdn.com/image.jpg", False),  # analytics subdomain
            ("https://myanalytics.com/image.jpg", True),  # analytics in domain name
        ]

        for src, should_accept in test_cases:
            doc = JustHTML(f'<img src="{src}">', safe=False)
            node = doc.query("img")[0]
            result = _has_valid_image_src(node)
            assert result == should_accept, (
                f"URL {src} should be {'accepted' if should_accept else 'rejected'}"
            )

    def test_malformed_url_handling(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        # Test malformed URLs that could cause exceptions
        malformed_urls = [
            "://invalid-url",  # Missing protocol
            "http://",  # No domain
            "https://domain",  # Domain without path, no slash
        ]

        for src in malformed_urls:
            doc = JustHTML(f'<img src="{src}">', safe=False)
            node = doc.query("img")[0]
            # Should not crash and should handle gracefully
            result = _has_valid_image_src(node)
            assert isinstance(result, bool)

    def test_filename_validation_edge_cases(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        # Test filename validation edge cases
        test_cases = [
            ("file.txt", False),  # Invalid extension
            ("image", False),  # No extension
            ("image.", False),  # Empty extension
            ("image.unknown", False),  # Unknown extension
        ]

        for src, should_accept in test_cases:
            doc = JustHTML(f'<img src="{src}">', safe=False)
            node = doc.query("img")[0]
            result = _has_valid_image_src(node)
            assert result == should_accept, (
                f"Filename {src} should be {'accepted' if should_accept else 'rejected'}"
            )

    def test_tracking_pixel_rejected(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="/pixel.gif">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_spacer_image_rejected(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="/spacer.gif">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_empty_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_whitespace_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="  ">', safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_missing_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML("<img>", safe=False)
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_no_attrs(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        class _Node:
            attrs = None

        assert _has_valid_image_src(_Node()) is False


@pytest.mark.unit
class TestNodeHasVisibleContent:
    def test_node_with_text(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p>Text</p>", safe=False)
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is True

    def test_node_with_image(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML('<p><img src="pic.png"></p>', safe=False)
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is True

    def test_empty_node(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p></p>", safe=False)
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is False

    def test_whitespace_only(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p>   </p>", safe=False)
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is False

    def test_image_without_src(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p><img></p>", safe=False)
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is False
