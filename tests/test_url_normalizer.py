"""Tests for URL normalization module."""

import pytest
from justhtml import JustHTML


@pytest.mark.unit
class TestAbsolutizeUrls:
    def test_absolutize_img_src(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<img src="images/pic.png">')
        node = doc.query("img")[0]
        absolutize_urls(node, "https://example.com/base/")

        assert node.attrs["src"] == "https://example.com/base/images/pic.png"

    def test_absolutize_root_media_node(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<img src="images/pic.png">')
        node = doc.query("img")[0]
        absolutize_urls(node, "https://example.com/base/")

        assert node.attrs["src"] == "https://example.com/base/images/pic.png"

    def test_absolutize_nested_images(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<div><img src="/img/one.png"><img src="/img/two.png"></div>')
        root = doc.query("div")[0]
        absolutize_urls(root, "https://example.com/")

        imgs = doc.query("img")
        assert imgs[0].attrs["src"] == "https://example.com/img/one.png"
        assert imgs[1].attrs["src"] == "https://example.com/img/two.png"

    def test_absolutize_srcset(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<img srcset="/img/small.jpg 1x, /img/large.jpg 2x">')
        node = doc.query("img")[0]
        absolutize_urls(node, "https://example.com/")

        srcset = node.attrs["srcset"]
        assert "https://example.com/img/small.jpg 1x" in srcset
        assert "https://example.com/img/large.jpg 2x" in srcset

    def test_absolutize_anchor_href(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<div><a href="/docs">Link</a></div>')
        root = doc.query("div")[0]
        absolutize_urls(root, "https://example.com/")

        assert doc.query("a")[0].attrs["href"] == "https://example.com/docs"

    def test_absolutize_video_elements(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<video src="/vid.mp4" poster="/poster.jpg"></video>')
        node = doc.query("video")[0]
        absolutize_urls(node, "https://example.com/")

        assert node.attrs["src"] == "https://example.com/vid.mp4"
        assert node.attrs["poster"] == "https://example.com/poster.jpg"

    def test_absolutize_noop_on_absolute_urls(self):
        from article_extractor.url_normalizer import absolutize_urls

        doc = JustHTML('<img src="https://cdn.example.com/img.png">')
        node = doc.query("img")[0]
        absolutize_urls(node, "https://example.com/")

        assert node.attrs["src"] == "https://cdn.example.com/img.png"


@pytest.mark.unit
class TestNormalizeSrcset:
    def test_normalize_srcset_handles_empty_and_plain_entries(self):
        from article_extractor.url_normalizer import _normalize_srcset

        normalized = _normalize_srcset(
            " , /img/one.jpg, /img/two.jpg 2x",
            "https://example.com/base/",
        )

        assert "https://example.com/img/one.jpg" in normalized
        assert "https://example.com/img/two.jpg 2x" in normalized

    def test_normalize_srcset_with_descriptors(self):
        from article_extractor.url_normalizer import _normalize_srcset

        normalized = _normalize_srcset(
            "/img/small.jpg 1x, /img/large.jpg 2x",
            "https://example.com/",
        )

        assert "https://example.com/img/small.jpg 1x" in normalized
        assert "https://example.com/img/large.jpg 2x" in normalized

    def test_normalize_srcset_with_width_descriptors(self):
        from article_extractor.url_normalizer import _normalize_srcset

        normalized = _normalize_srcset(
            "/img/small.jpg 100w, /img/large.jpg 200w",
            "https://example.com/",
        )

        assert "https://example.com/img/small.jpg 100w" in normalized
        assert "https://example.com/img/large.jpg 200w" in normalized

    def test_normalize_srcset_empty_string(self):
        from article_extractor.url_normalizer import _normalize_srcset

        normalized = _normalize_srcset("", "https://example.com/")
        assert normalized == ""

    def test_normalize_srcset_only_commas(self):
        from article_extractor.url_normalizer import _normalize_srcset

        normalized = _normalize_srcset(", , ,", "https://example.com/")
        assert normalized == ""


@pytest.mark.unit
class TestRewriteUrlAttributes:
    def test_rewrite_url_attributes_no_attrs(self):
        from article_extractor.url_normalizer import _rewrite_url_attributes

        class _AttrlessNode:
            attrs = None

        # Should not raise
        _rewrite_url_attributes(
            _AttrlessNode(),
            ("href",),
            "https://example.com",
        )

    def test_rewrite_url_attributes_missing_attribute(self):
        from article_extractor.url_normalizer import _rewrite_url_attributes

        class _Node:
            attrs = {}

        node = _Node()
        _rewrite_url_attributes(node, ("href",), "https://example.com")
        assert "href" not in node.attrs

    def test_rewrite_url_attributes_empty_value(self):
        from article_extractor.url_normalizer import _rewrite_url_attributes

        class _Node:
            attrs = {"href": ""}

        node = _Node()
        _rewrite_url_attributes(node, ("href",), "https://example.com")
        assert node.attrs["href"] == ""

    def test_rewrite_url_attributes_simple_href(self):
        from article_extractor.url_normalizer import _rewrite_url_attributes

        class _Node:
            attrs = {"href": "/docs"}

        node = _Node()
        _rewrite_url_attributes(node, ("href",), "https://example.com/")
        assert node.attrs["href"] == "https://example.com/docs"
