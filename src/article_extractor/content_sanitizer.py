"""Content sanitization for extracted articles.

Deep module that removes empty or useless DOM nodes from extracted content.
Hides DOM manipulation complexity behind a simple interface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .dom_utils import collect_nodes_by_tags

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


def sanitize_content(node: SimpleDomNode) -> None:
    """Remove empty and useless nodes from extracted content.

    Simple interface that hides DOM traversal and manipulation complexity.
    Removes:
    - Empty links (no visible text or images)
    - Images without valid src attributes
    - Empty block elements (p, li, div with no content)

    Args:
        node: Root content node to sanitize (modified in place)

    Example:
        >>> sanitize_content(article_node)
    """
    _remove_empty_links(node)
    _remove_empty_images(node)
    _remove_empty_blocks(node)


def _remove_empty_links(root: SimpleDomNode) -> None:
    """Drop anchor tags that would render as empty markdown links."""
    _remove_nodes(root, ("a",), keep=_node_has_visible_content)


def _remove_empty_images(root: SimpleDomNode) -> None:
    """Remove <img> elements without a usable src attribute."""
    _remove_nodes(root, ("img",), keep=_has_valid_image_src)


def _remove_empty_blocks(root: SimpleDomNode) -> None:
    """Strip block-level nodes that no longer carry content."""
    target_tags = ("li", "p", "div")
    _remove_nodes(root, target_tags, keep=_node_has_visible_content)


def _remove_nodes(
    root: SimpleDomNode,
    tags: tuple[str, ...],
    *,
    keep: Callable[[SimpleDomNode], bool],
) -> None:
    """Remove nodes for tags when they fail the keep predicate."""
    for node in collect_nodes_by_tags(root, tags):
        if keep(node):
            continue

        parent = getattr(node, "parent", None)
        if parent is not None:
            parent.remove_child(node)


def _has_valid_image_src(node: SimpleDomNode) -> bool:
    """Check whether an image node has a non-empty src attribute."""
    attrs = getattr(node, "attrs", {}) or {}
    src = attrs.get("src")
    if src is None:
        return False

    return bool(str(src).strip())


def _node_has_visible_content(node: SimpleDomNode) -> bool:
    """Determine whether a node contains text or media worth keeping."""
    text = node.to_text(strip=True)
    if text:
        return True

    return any(_has_valid_image_src(img) for img in node.query("img"))
