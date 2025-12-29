"""Instance-level caching for article extraction.

Provides ExtractionCache class for per-extraction caching without module-level state.
This allows parallel async usage without side effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


class ExtractionCache:
    """Per-extraction cache for node text and link density.

    Create a new instance for each document extraction to avoid
    cross-document pollution in async/parallel contexts.

    Example:
        cache = ExtractionCache()
        text = cache.get_node_text(node)
        density = cache.get_link_density(node)
    """

    __slots__ = ("_text_cache", "_link_density_cache")

    def __init__(self) -> None:
        """Initialize empty caches."""
        self._text_cache: dict[int, str] = {}
        self._link_density_cache: dict[int, float] = {}

    def get_node_text(self, node: SimpleDomNode) -> str:
        """Get text content with caching.

        Args:
            node: A JustHTML SimpleDomNode

        Returns:
            Text content (cached per extraction)
        """
        node_id = id(node)
        if node_id not in self._text_cache:
            self._text_cache[node_id] = node.to_text(separator=" ", strip=True)
        return self._text_cache[node_id]

    def get_text_length(self, node: SimpleDomNode) -> int:
        """Get the length of text content in a node.

        Args:
            node: A JustHTML SimpleDomNode

        Returns:
            Length of text content
        """
        return len(self.get_node_text(node))

    def get_link_density(self, node: SimpleDomNode) -> float:
        """Calculate the ratio of link text to total text.

        High link density indicates navigation/boilerplate.
        Results are cached per extraction.

        Args:
            node: A JustHTML SimpleDomNode

        Returns:
            Ratio of link text to total text (0.0 to 1.0)
        """
        node_id = id(node)
        if node_id in self._link_density_cache:
            return self._link_density_cache[node_id]

        text = self.get_node_text(node)
        if not text:
            self._link_density_cache[node_id] = 0.0
            return 0.0

        text_length = len(text)

        # Sum up text inside all links
        link_length = 0
        for link in node.query("a"):
            link_text = self.get_node_text(link)
            link_length += len(link_text)

        density = link_length / text_length
        self._link_density_cache[node_id] = density
        return density

    def clear(self) -> None:
        """Clear all caches. Called automatically when extraction completes."""
        self._text_cache.clear()
        self._link_density_cache.clear()
