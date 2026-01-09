"""Document cleaning for HTML article extraction.

Deep module that removes non-content elements (scripts, styles, navigation).
Hides CSS selector complexity and DOM manipulation behind a simple interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from justhtml import JustHTML


def clean_document(doc: JustHTML, strip_selector: str, role_selector: str) -> JustHTML:
    """Remove non-content elements from HTML document.

    Simple interface that hides selector construction and DOM traversal complexity.
    Removes:
    - Scripts, styles, and other boilerplate tags
    - Elements with navigation/dialog roles

    Args:
        doc: JustHTML document to clean (modified in place)
        strip_selector: CSS selector for tags to remove
        role_selector: CSS selector for ARIA roles to remove

    Returns:
        The same document (cleaned in place)

    Example:
        >>> clean_document(doc, STRIP_SELECTOR, ROLE_SELECTOR)
    """
    _remove_nodes_by_selector(doc, strip_selector)
    _remove_nodes_by_selector(doc, role_selector)
    return doc


def _remove_nodes_by_selector(doc: JustHTML, selector: str) -> None:
    """Remove all nodes matching a selector when they have a parent.

    Safely handles nodes without parents (e.g., already detached nodes).
    Skips processing if selector is empty.
    """
    if not selector or not selector.strip():
        return

    for node in doc.query(selector):
        parent = getattr(node, "parent", None)
        if parent is not None:
            parent.remove_child(node)
