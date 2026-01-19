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

_TRACKING_FILENAMES = frozenset(
    {
        "pixel.gif",
        "pixel.png",
        "1x1.gif",
        "1x1.png",
        "spacer.gif",
        "spacer.png",
        "blank.gif",
        "blank.png",
    }
)
_TRACKING_DOMAIN_PREFIXES = ("tracking.", "analytics.", "metrics.")
_SAFE_IMAGE_DATA_PREFIXES = (
    "data:image/png",
    "data:image/jpeg",
    "data:image/jpg",
    "data:image/gif",
    "data:image/webp",
    "data:image/avif",
    "data:image/bmp",
)


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

    src_str = str(src).strip()
    if not src_str:
        return False

    src_lower = src_str.lower()

    if src_lower.startswith("data:"):
        return _is_safe_image_data_url(src_lower)

    filename = _extract_filename(src_lower)
    domain = _extract_domain(src_lower)
    if filename in _TRACKING_FILENAMES or (
        domain
        and any(domain.startswith(prefix) for prefix in _TRACKING_DOMAIN_PREFIXES)
    ):
        return False

    # Keep images with data URLs, absolute URLs, protocol-relative, or obvious relative paths
    if src_lower.startswith(("http://", "https://", "//")):
        is_valid = _is_valid_absolute_image_filename(filename)
    elif src_lower.startswith(("/", "./", "../")):
        is_valid = True
    else:
        is_valid = _is_valid_image_filename(src_lower)

    return is_valid


def _is_valid_image_filename(filename: str) -> bool:
    """Check if a bare filename looks like a valid image file."""
    # Require a common image extension and a minimally descriptive basename to avoid
    # accepting tiny tracking pixels such as "t.gif" or "p.png"
    filename = filename.split("/")[-1]
    name, dot, ext = filename.rpartition(".")
    if not dot:
        return False

    valid_extensions = {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "svg",
        "bmp",
        "avif",
        "apng",
        "tiff",
        "jfif",
    }

    if ext not in valid_extensions:
        return False

    # Require at least a few characters in the basename to filter out trackers like "t.gif"
    return len(name.strip()) >= 2  # Allow "bg.jpg" but reject "t.gif"


def _is_valid_absolute_image_filename(filename: str) -> bool:
    """Check if absolute URL filenames look like plausible image files."""
    if not filename:
        return True
    if "." not in filename:
        return True
    return _is_valid_image_filename(filename)


def _is_safe_image_data_url(src_lower: str) -> bool:
    """Allow only safe image MIME types in data URLs."""
    return src_lower.startswith(_SAFE_IMAGE_DATA_PREFIXES)


def _extract_domain(src_lower: str) -> str | None:
    """Extract domain from absolute or protocol-relative URLs."""
    if src_lower.startswith("//"):
        remainder = src_lower[2:]
    elif "://" in src_lower:
        remainder = src_lower.split("://", 1)[1]
    else:
        return None

    if not remainder:
        return None

    domain = remainder.split("/", 1)[0]
    domain = domain.split("?", 1)[0].split("#", 1)[0]
    return domain


def _extract_filename(src_lower: str) -> str:
    """Extract filename from a URL-like string."""
    path = src_lower.split("?", 1)[0].split("#", 1)[0]
    return path.rsplit("/", 1)[-1]


def _node_has_visible_content(node: SimpleDomNode) -> bool:
    """Determine whether a node contains text or media worth keeping."""
    text = node.to_text(strip=True)
    if text:
        return True

    return any(_has_valid_image_src(img) for img in node.query("img"))
