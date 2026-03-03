"""Candidate finding for article extraction.

Provides logic to identify and rank potential content containers in HTML documents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cache import ExtractionCache
from .constants import MIN_CHAR_THRESHOLD
from .scorer import is_unlikely_candidate, rank_candidates
from .types import ScoredCandidate

if TYPE_CHECKING:
    from justhtml import JustHTML
    from justhtml.node import SimpleDomNode

_SEMANTIC_CANDIDATE_TAGS = ("article", "main")
_SEMANTIC_CANDIDATE_SELECTORS = ('[role="main"]',)
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

    # Refine broad wrappers (e.g. page shell divs) toward article-like descendants.
    refined = _refine_candidate(ranked)
    return refined.node


def _find_candidates(doc: JustHTML, cache: ExtractionCache) -> list[SimpleDomNode]:
    """Find potential content container candidates."""
    # Look for semantic article containers first (fast path)
    seen: set[int] = set()
    candidates: list[SimpleDomNode] = []

    def add_if_new(node: SimpleDomNode) -> None:
        node_id = id(node)
        if node_id not in seen and not is_unlikely_candidate(node):
            seen.add(node_id)
            candidates.append(node)

    # Semantic tags: article, main
    for tag in _SEMANTIC_CANDIDATE_TAGS:
        for node in doc.query(tag):
            add_if_new(node)

    # Semantic selectors: [role="main"]
    for selector in _SEMANTIC_CANDIDATE_SELECTORS:
        for node in doc.query(selector):
            add_if_new(node)

    # If we found semantic containers, use them directly
    if candidates:
        return candidates

    # Fallback: scan divs and sections with minimum content
    for tag in _FALLBACK_CANDIDATE_TAGS:
        for node in doc.query(tag):
            if cache.get_text_length(node) > MIN_CHAR_THRESHOLD:
                add_if_new(node)

    return candidates


_DESCENDANT_SCORE_RATIO = 0.9
_DESCENDANT_LENGTH_RATIO = 0.5
_LINK_DENSITY_IMPROVEMENT = 0.8
_MAX_REFINEMENT_DEPTH = 3


def _refine_candidate(ranked: list[ScoredCandidate]) -> ScoredCandidate:
    """Prefer strong descendants when top candidate is an over-broad container."""
    if not ranked:
        raise ValueError("ranked candidates cannot be empty")

    current = ranked[0]
    for _ in range(_MAX_REFINEMENT_DEPTH):
        child = _pick_stronger_descendant(current, ranked)
        if child is None:
            break
        current = child
    return current


def _pick_stronger_descendant(
    current: ScoredCandidate, ranked: list[ScoredCandidate]
) -> ScoredCandidate | None:
    """Find descendant candidate with near-equal score but cleaner density."""
    current_score = max(current.score, 0.1)
    current_length = max(current.content_length, MIN_CHAR_THRESHOLD)
    current_density = max(current.link_density, 0.0)

    options: list[ScoredCandidate] = []
    for candidate in ranked:
        if candidate is current:
            continue
        if candidate.content_length < MIN_CHAR_THRESHOLD:
            continue
        if not _is_descendant(candidate.node, current.node):
            continue
        if candidate.score < current_score * _DESCENDANT_SCORE_RATIO:
            continue
        if candidate.content_length < current_length * _DESCENDANT_LENGTH_RATIO:
            continue

        # Require a meaningful link-density improvement unless already very clean.
        cleaner_density = (
            candidate.link_density <= current_density * _LINK_DENSITY_IMPROVEMENT
            or candidate.link_density <= 0.05
        )
        if not cleaner_density:
            continue
        options.append(candidate)

    if not options:
        return None

    # Prefer highest score, then lower link density, then shorter content length.
    options.sort(key=lambda c: (-c.score, c.link_density, c.content_length))
    return options[0]


def _is_descendant(node: SimpleDomNode, ancestor: SimpleDomNode) -> bool:
    """Return True when node is a strict descendant of ancestor."""
    parent = getattr(node, "parent", None)
    while parent is not None:
        if parent is ancestor:
            return True
        parent = getattr(parent, "parent", None)
    return False
