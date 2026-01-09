"""DOM traversal utilities for article extraction.

General-purpose helpers for working with JustHTML DOM nodes.
These utilities are reusable across content sanitization, URL normalization,
and other DOM manipulation tasks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


def collect_nodes_by_tags(
    root: SimpleDomNode, tags: tuple[str, ...]
) -> list[SimpleDomNode]:
    """Collect all nodes matching given tag names, including root if it matches.

    Args:
        root: Root DOM node to search from
        tags: Tuple of tag names to match (case-insensitive)

    Returns:
        List of matching nodes (may include root if it matches)

    Example:
        nodes = collect_nodes_by_tags(doc.root, ("a", "img"))
        # Returns all links and images in the document
    """
    nodes: list[SimpleDomNode] = []
    for tag in tags:
        nodes.extend(root.query(tag))

    root_tag = getattr(root, "name", "").lower()
    if root_tag in tags:
        nodes.append(root)

    return nodes
