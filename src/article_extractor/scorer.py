"""Content scoring engine for article extraction.

Implements Readability.js-style scoring algorithm to identify
the main content container in an HTML document.

All scoring functions accept an ExtractionCache instance for thread-safe
caching without module-level state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .constants import (
    COMMA_RE,
    LINK_DENSITY_THRESHOLD,
    MIN_PARAGRAPH_LENGTH,
    NEGATIVE_SCORE_RE,
    OK_MAYBE_RE,
    PHOTO_HINTS_RE,
    POSITIVE_SCORE_RE,
    READABILITY_ASSET_RE,
    TAG_SCORES,
    UNLIKELY_CANDIDATES_RE,
)

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode

    from .cache import ExtractionCache
    from .types import ScoredCandidate


def get_class_id_string(node: SimpleDomNode) -> str:
    """Get combined class and id string for pattern matching.

    Args:
        node: A JustHTML SimpleDomNode

    Returns:
        Combined class and id string
    """
    attrs = node.attrs or {}
    class_str = attrs.get("class", "")
    id_str = attrs.get("id", "")

    # Handle class as list or string
    if isinstance(class_str, list):
        class_str = " ".join(class_str)

    return f"{class_str} {id_str}"


def get_tag_score(tag_name: str) -> int:
    """Get base score for a tag.

    Args:
        tag_name: HTML tag name (lowercase)

    Returns:
        Base score for the tag
    """
    return TAG_SCORES.get(tag_name.lower(), 0)


def get_class_weight(node: SimpleDomNode) -> float:
    """Calculate score weight based on class/id attributes.

    Positive patterns (article, content, main) add +25
    Negative patterns (sidebar, footer, comment) subtract -25

    Args:
        node: A JustHTML SimpleDomNode

    Returns:
        Score weight (-50 to +50)
    """
    weight = 0.0
    class_id = get_class_id_string(node)

    if not class_id.strip():
        return weight

    # Check positive patterns
    if POSITIVE_SCORE_RE.search(class_id):
        weight += 25

    # Check negative patterns
    if NEGATIVE_SCORE_RE.search(class_id):
        weight -= 25

    # Bonus for photo hints (keep images)
    if PHOTO_HINTS_RE.search(class_id):
        weight += 10

    # Bonus for Readability asset class
    if READABILITY_ASSET_RE.search(class_id):
        weight += 25

    return weight


def is_unlikely_candidate(node: SimpleDomNode) -> bool:
    """Check if a node is unlikely to contain main content.

    Args:
        node: A JustHTML SimpleDomNode

    Returns:
        True if node should be skipped
    """
    class_id = get_class_id_string(node)

    if not class_id.strip():
        return False

    # Check unlikely patterns (but allow if it also matches OK_MAYBE patterns)
    if UNLIKELY_CANDIDATES_RE.search(class_id):
        return not OK_MAYBE_RE.search(class_id)

    return False


def count_commas(text: str) -> int:
    """Count commas in text (content signal).

    Args:
        text: Text to count commas in

    Returns:
        Number of commas
    """
    return len(COMMA_RE.findall(text))


def score_paragraph(node: SimpleDomNode, cache: ExtractionCache) -> float:
    """Score a paragraph element based on content signals.

    Follows Readability.js paragraph scoring:
    - Base: +1 for paragraph itself
    - +1 per comma (content signal)
    - +1 per 100 chars, max 3

    Args:
        node: A JustHTML SimpleDomNode (should be <p> or similar)
        cache: ExtractionCache instance for text caching

    Returns:
        Paragraph score
    """
    text = cache.get_node_text(node)
    text_length = len(text)

    # Skip very short paragraphs
    if text_length < MIN_PARAGRAPH_LENGTH:
        return 0.0

    # Base score
    score = 1.0

    # Comma bonus (content signal)
    score += count_commas(text)

    # Length bonus (max 3)
    score += min(text_length // 100, 3)

    return score


def score_node(node: SimpleDomNode) -> float:
    """Calculate content score for a node.

    Combines tag score, class weight, and content scoring.

    Args:
        node: A JustHTML SimpleDomNode

    Returns:
        Content score
    """
    tag_name = node.name.lower() if hasattr(node, "name") else ""

    # Start with tag-based score
    score = float(get_tag_score(tag_name))

    # Add class/id weight
    score += get_class_weight(node)

    return score


def calculate_content_score(
    node: SimpleDomNode,
    cache: ExtractionCache,
    scores: dict[int, float] | None = None,
) -> float:
    """Calculate accumulated content score for a candidate.

    Sums paragraph scores and propagates to ancestors:
    - Parent gets full paragraph score
    - Grandparent gets half
    - Great-grandparent+ gets 1/(level*3)

    Args:
        node: A JustHTML SimpleDomNode
        cache: ExtractionCache instance for caching
        scores: Optional dict to accumulate scores (keyed by node id)

    Returns:
        Total content score
    """
    if scores is None:
        scores = {}

    node_id = id(node)
    if node_id in scores:
        return scores[node_id]

    # Initialize with node's own score
    score = score_node(node)

    # Score paragraphs and propagate to ancestors
    for p in node.query("p"):
        p_score = score_paragraph(p, cache)
        if p_score > 0:
            # Add to this node's score
            score += p_score

    # Apply link density penalty
    link_density = cache.get_link_density(node)
    if link_density > LINK_DENSITY_THRESHOLD:
        score *= 1 - link_density

    scores[node_id] = score
    return score


def rank_candidates(
    candidates: list[SimpleDomNode],
    cache: ExtractionCache,
) -> list[ScoredCandidate]:
    """Rank candidate nodes by content score.

    Args:
        candidates: List of potential content containers
        cache: ExtractionCache instance for caching

    Returns:
        Sorted list of ScoredCandidate (highest score first)
    """
    from .types import ScoredCandidate

    scored = []
    for node in candidates:
        score = calculate_content_score(node, cache)
        text_length = cache.get_text_length(node)
        link_density = cache.get_link_density(node)

        scored.append(
            ScoredCandidate(
                node=node,
                score=score,
                content_length=text_length,
                link_density=link_density,
            )
        )

    # Sort by score (descending)
    scored.sort()
    return scored
