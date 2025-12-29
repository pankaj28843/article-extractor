"""Utility functions for article extraction.

Stateless helper functions for text processing.
No module-level caching - use ExtractionCache for cached operations.
"""

from __future__ import annotations


def get_word_count(text: str) -> int:
    """Count words in text.

    Args:
        text: Text to count words in

    Returns:
        Number of words
    """
    return len(text.split())


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    Collapses multiple spaces/newlines into single spaces.

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    return " ".join(text.split())


def extract_excerpt(text: str, max_length: int = 200) -> str:
    """Extract a short excerpt from text.

    Args:
        text: Text to extract excerpt from
        max_length: Maximum length of excerpt

    Returns:
        Excerpt string
    """
    text = normalize_whitespace(text)
    if len(text) <= max_length:
        return text

    # Try to break at word boundary
    excerpt = text[:max_length]
    last_space = excerpt.rfind(" ")
    if last_space > max_length * 0.7:  # Don't cut too short
        excerpt = excerpt[:last_space]

    return excerpt.rstrip() + "..."
