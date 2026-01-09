"""URL normalization for extracted article content.

Deep module that hides URL parsing complexity behind a simple interface.
Handles absolutization of relative URLs in links, images, and media elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

from .dom_utils import collect_nodes_by_tags

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


_URL_ATTR_MAP: dict[str, tuple[str, ...]] = {
    "a": ("href",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
}


def absolutize_urls(node: SimpleDomNode, base_url: str) -> None:
    """Rewrite relative URLs in a node tree to be absolute.

    Simple interface that hides URL parsing complexity.
    Handles links, images, and media elements with various attributes.

    Args:
        node: Root node to process (modified in place)
        base_url: Base URL for resolving relative URLs

    Example:
        >>> absolutize_urls(content_node, "https://example.com/page")
    """
    for tag, attributes in _URL_ATTR_MAP.items():
        for element in collect_nodes_by_tags(node, (tag,)):
            _rewrite_url_attributes(element, attributes, base_url)


def _rewrite_url_attributes(
    element: SimpleDomNode,
    attributes: tuple[str, ...],
    base_url: str,
) -> None:
    """Rewrite URL attributes on an element to be absolute."""
    attrs = getattr(element, "attrs", None)
    if not attrs:
        return

    for attribute in attributes:
        value = attrs.get(attribute)
        if not value:
            continue
        if attribute == "srcset":
            attrs[attribute] = _normalize_srcset(value, base_url)
        else:
            attrs[attribute] = urljoin(base_url, str(value))


def _normalize_srcset(value: str, base_url: str) -> str:
    """Normalize srcset attribute values to absolute URLs.

    srcset format: "url1 1x, url2 2x" or "url1 100w, url2 200w"
    """
    entries: list[str] = []
    for raw_entry in str(value).split(","):
        candidate = raw_entry.strip()
        if not candidate:
            continue
        if " " in candidate:
            url_part, descriptor = candidate.split(None, 1)
            entries.append(f"{urljoin(base_url, url_part)} {descriptor.strip()}")
        else:
            entries.append(urljoin(base_url, candidate))
    return ", ".join(entries)
