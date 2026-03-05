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

    # Also scan div/section containers even when semantic nodes are present.
    # Many pages wrap article bodies inside <main>/<article> plus extra chrome.
    for tag in _FALLBACK_CANDIDATE_TAGS:
        for node in doc.query(tag):
            if cache.get_text_length(node) > MIN_CHAR_THRESHOLD:
                add_if_new(node)

    return candidates


_DESCENDANT_SCORE_RATIO = 0.85
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
        required_score_ratio = _DESCENDANT_SCORE_RATIO
        # Allow deeper narrowing when a broad wrapper has much higher link-density
        # and a descendant is substantially shorter/cleaner.
        if (
            current_density > 0.06
            and candidate.link_density < 0.03
            and candidate.content_length < current_length * 0.4
        ):
            required_score_ratio = min(required_score_ratio, 0.3)

        candidate_tag = (
            candidate.node.name.lower() if hasattr(candidate.node, "name") else ""
        )
        if (
            candidate_tag == "article"
            and candidate.link_density < current_density * 0.7
        ):
            required_score_ratio = min(required_score_ratio, 0.65)

        if candidate.score < current_score * required_score_ratio:
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
