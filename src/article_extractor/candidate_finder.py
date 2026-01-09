"""Candidate finding for article extraction.

Provides logic to identify and rank potential content containers in HTML documents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cache import ExtractionCache
from .constants import MIN_CHAR_THRESHOLD
from .scorer import is_unlikely_candidate, rank_candidates

if TYPE_CHECKING:
    from justhtml import JustHTML
    from justhtml.node import SimpleDomNode

_SEMANTIC_CANDIDATE_TAGS = ("article", "main")
_FALLBACK_CANDIDATE_TAGS = ("div", "section")


def find_top_candidate(doc: JustHTML, cache: ExtractionCache) -> SimpleDomNode | None:
    """Find the best content container using Readability algorithm.

    Args:
        doc: Parsed HTML document
        cache: Extraction cache for text length lookups

    Returns:
        Top-ranked candidate node or None if no candidates found
    """
    candidates = _find_candidates(doc, cache)

    if not candidates:
        # Fallback: look for body
        body_nodes = doc.query("body")
        if body_nodes:
            candidates = [body_nodes[0]]

    if not candidates:
        return None

    # Rank candidates by content score
    ranked = rank_candidates(candidates, cache)

    if not ranked:
        return None

    # Return the top candidate
    return ranked[0].node


def _find_candidates(doc: JustHTML, cache: ExtractionCache) -> list[SimpleDomNode]:
    """Find potential content container candidates."""
    # Look for semantic article containers first (fast path)
    candidates: list[SimpleDomNode] = []
    for tag in _SEMANTIC_CANDIDATE_TAGS:
        candidates.extend(_candidate_nodes(doc, cache, tag))

    # If we found semantic containers, use them directly
    if candidates:
        return candidates

    # Fallback: scan divs and sections
    for tag in _FALLBACK_CANDIDATE_TAGS:
        candidates.extend(
            _candidate_nodes(doc, cache, tag, min_length=MIN_CHAR_THRESHOLD)
        )

    return candidates


def _candidate_nodes(
    doc: JustHTML,
    cache: ExtractionCache,
    tag: str,
    *,
    min_length: int | None = None,
) -> list[SimpleDomNode]:
    """Collect candidate nodes for a tag with optional length filtering."""
    candidates: list[SimpleDomNode] = []
    for node in doc.query(tag):
        if is_unlikely_candidate(node):
            continue
        if min_length is not None and cache.get_text_length(node) <= min_length:
            continue
        candidates.append(node)
    return candidates
