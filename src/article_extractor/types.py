"""Type definitions for article extraction.

Provides ArticleResult and ExtractionOptions dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from justhtml.node import SimpleDomNode


@dataclass
class ArticleResult:
    """Result from pure-Python article extraction."""

    url: str
    title: str
    content: str  # Clean HTML content
    markdown: str  # Markdown version
    excerpt: str  # First ~200 chars
    word_count: int
    success: bool
    error: str | None = None
    author: str | None = None
    date_published: str | None = None
    language: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractionOptions:
    """Options for article extraction."""

    min_word_count: int = 150
    min_char_threshold: int = 500
    include_images: bool = True
    include_code_blocks: bool = True
    safe_markdown: bool = True  # Use JustHTML safe sanitization


@dataclass
class ScoredCandidate:
    """A DOM node with its content score."""

    node: SimpleDomNode
    score: float
    content_length: int = 0
    link_density: float = 0.0

    def __lt__(self, other: ScoredCandidate) -> bool:
        """Allow sorting by score (descending)."""
        return self.score > other.score  # Higher score = better
