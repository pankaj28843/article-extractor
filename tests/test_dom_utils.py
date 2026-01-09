"""Tests for DOM utilities module."""

from justhtml import JustHTML

from article_extractor.dom_utils import collect_nodes_by_tags


def test_collect_nodes_basic():
    """Test collecting nodes by tag names."""
    html = """
    <div>
        <p>First paragraph</p>
        <p>Second paragraph</p>
        <a href="/">Link</a>
    </div>
    """
    doc = JustHTML(html)
    paragraphs = collect_nodes_by_tags(doc.root, ("p",))
    assert len(paragraphs) == 2
    assert all(p.name == "p" for p in paragraphs)


def test_collect_nodes_multiple_tags():
    """Test collecting nodes with multiple tag types."""
    html = """
    <div>
        <p>Text</p>
        <img src="test.jpg">
        <a href="/">Link</a>
        <img src="test2.jpg">
    </div>
    """
    doc = JustHTML(html)
    nodes = collect_nodes_by_tags(doc.root, ("p", "img"))
    assert len(nodes) == 3  # 1 p + 2 img
    tags = {n.name for n in nodes}
    assert tags == {"p", "img"}


def test_collect_nodes_includes_root_if_matches():
    """Test that root node is included when it matches the tag."""
    html = "<p>Root paragraph</p>"
    doc = JustHTML(html)
    paragraphs = collect_nodes_by_tags(doc.root, ("p",))
    assert len(paragraphs) == 1
    assert paragraphs[0].name == "p"
    assert paragraphs[0].to_text() == "Root paragraph"


def test_collect_nodes_empty_tags_tuple():
    """Test collecting with empty tags tuple returns empty list."""
    html = "<div><p>Text</p></div>"
    doc = JustHTML(html)
    nodes = collect_nodes_by_tags(doc.root, ())
    # Should only include root if it somehow matches empty tuple
    # In practice, this returns empty list as getattr returns "" which is not in ()
    assert nodes == []


def test_collect_nodes_nested_structure():
    """Test collecting nodes from nested structure."""
    html = """
    <div>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
        </ul>
    </div>
    """
    doc = JustHTML(html)
    items = collect_nodes_by_tags(doc.root, ("li",))
    assert len(items) == 3


def test_collect_nodes_no_matches():
    """Test collecting when no nodes match the tags."""
    html = "<div><p>Text</p></div>"
    doc = JustHTML(html)
    images = collect_nodes_by_tags(doc.root, ("img",))
    assert images == []


def test_collect_nodes_case_insensitive():
    """Test that tag matching is case-insensitive."""
    html = "<DIV><P>Text</P></DIV>"
    doc = JustHTML(html)
    # Tags are normalized to lowercase
    paragraphs = collect_nodes_by_tags(doc.root, ("p",))
    assert len(paragraphs) == 1


def test_collect_nodes_complex_document():
    """Test collecting from a complex document structure."""
    html = """
    <article>
        <h1>Title</h1>
        <p>Intro</p>
        <div class="content">
            <p>First paragraph</p>
            <blockquote><p>Quote paragraph</p></blockquote>
            <p>Second paragraph</p>
        </div>
        <footer><p>Footer paragraph</p></footer>
    </article>
    """
    doc = JustHTML(html)
    paragraphs = collect_nodes_by_tags(doc.root, ("p",))
    # Root is <article>, so we get 5 p tags total (not including root)
    assert len(paragraphs) == 5  # Intro + First + Quote + Second + Footer

    # Collect multiple types
    headers_and_paras = collect_nodes_by_tags(doc.root, ("h1", "p"))
    assert len(headers_and_paras) == 6  # 1 h1 + 5 p
