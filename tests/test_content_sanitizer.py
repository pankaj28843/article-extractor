"""Tests for content sanitization module."""

import pytest
from justhtml import JustHTML


@pytest.mark.unit
class TestSanitizeContent:
    def test_sanitize_removes_empty_links(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><a href="/link"></a><p>Text</p></div>')
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("a")) == 0
        assert len(doc.query("p")) == 1

    def test_sanitize_keeps_links_with_text(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><a href="/link">Link text</a></div>')
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("a")) == 1

    def test_sanitize_removes_images_without_src(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<div><img><p>Text</p></div>")
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("img")) == 0
        assert len(doc.query("p")) == 1

    def test_sanitize_keeps_images_with_src(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><img src="image.png"></div>')
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("img")) == 1

    def test_sanitize_removes_empty_paragraphs(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<div><p>   </p><p>Real text</p></div>")
        root = doc.query("div")[0]
        sanitize_content(root)

        paragraphs = doc.query("p")
        assert len(paragraphs) == 1
        assert "Real text" in paragraphs[0].to_text()

    def test_sanitize_removes_empty_list_items(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<ul><li></li><li>Item</li></ul>")
        root = doc.query("ul")[0]
        sanitize_content(root)

        items = doc.query("li")
        assert len(items) == 1
        assert "Item" in items[0].to_text()

    def test_sanitize_removes_empty_divs(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("<div><div class='wrapper'></div><div>Content</div></div>")
        root = doc.query("div")[0]
        sanitize_content(root)

        # Root div still exists, but empty wrapper div is removed
        divs = root.query("div")
        assert len(divs) == 1
        assert "Content" in divs[0].to_text()

    def test_sanitize_keeps_blocks_with_images(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML('<div><p><img src="pic.png"></p></div>')
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("p")) == 1
        assert len(doc.query("img")) == 1

    def test_sanitize_combined_cleanup(self):
        from article_extractor.content_sanitizer import sanitize_content

        doc = JustHTML("""
            <div>
                <a></a>
                <img>
                <p></p>
                <p>Good content</p>
                <a href="/link">Good link</a>
                <img src="good.png">
            </div>
        """)
        root = doc.query("div")[0]
        sanitize_content(root)

        assert len(doc.query("a")) == 1
        assert len(doc.query("img")) == 1
        assert len(doc.query("p")) == 1


@pytest.mark.unit
class TestRemoveEmptyLinks:
    def test_remove_empty_anchor_root(self):
        from article_extractor.content_sanitizer import _remove_empty_links

        doc = JustHTML('<div><a href="https://example.com"></a></div>')
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

        doc = JustHTML("<div><img></div>")
        node = doc.query("img")[0]
        _remove_empty_images(node)

        assert doc.query("img") == []

    def test_keeps_image_with_valid_src(self):
        from article_extractor.content_sanitizer import _remove_empty_images

        doc = JustHTML('<div><img src="pic.png"></div>')
        root = doc.query("div")[0]
        _remove_empty_images(root)

        assert len(doc.query("img")) == 1

    def test_removes_image_with_empty_src(self):
        from article_extractor.content_sanitizer import _remove_empty_images

        doc = JustHTML('<div><img src=""></div>')
        root = doc.query("div")[0]
        _remove_empty_images(root)

        assert len(doc.query("img")) == 0


@pytest.mark.unit
class TestRemoveEmptyBlocks:
    def test_remove_empty_block_root(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML("<div><p>   </p></div>")
        node = doc.query("p")[0]
        _remove_empty_blocks(node)

        assert doc.query("p") == []

    def test_keeps_blocks_with_text(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML("<div><p>Text</p></div>")
        root = doc.query("div")[0]
        _remove_empty_blocks(root)

        assert len(doc.query("p")) == 1

    def test_keeps_blocks_with_images(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML('<div><div><img src="pic.png"></div></div>')
        root = doc.query("div")[0]
        _remove_empty_blocks(root)

        # Root div still there, inner div kept (has image)
        assert len(root.query("div")) == 1

    def test_removes_nested_empty_blocks(self):
        from article_extractor.content_sanitizer import _remove_empty_blocks

        doc = JustHTML("<div><div><p></p></div><div>Content</div></div>")
        root = doc.query("div")[0]
        _remove_empty_blocks(root)

        # Empty paragraph removed, but divs remain (one has content)
        assert len(doc.query("p")) == 0


@pytest.mark.unit
class TestHasValidImageSrc:
    def test_valid_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="pic.png">')
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is True

    def test_empty_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="">')
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_whitespace_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML('<img src="  ">')
        node = doc.query("img")[0]
        assert _has_valid_image_src(node) is False

    def test_missing_src(self):
        from article_extractor.content_sanitizer import _has_valid_image_src

        doc = JustHTML("<img>")
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

        doc = JustHTML("<p>Text</p>")
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is True

    def test_node_with_image(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML('<p><img src="pic.png"></p>')
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is True

    def test_empty_node(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p></p>")
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is False

    def test_whitespace_only(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p>   </p>")
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is False

    def test_image_without_src(self):
        from article_extractor.content_sanitizer import (
            _node_has_visible_content,
        )

        doc = JustHTML("<p><img></p>")
        node = doc.query("p")[0]
        assert _node_has_visible_content(node) is False
