"""Retry and backoff utilities for network operations.

Provides shared backoff strategies for retryable operations across
fetchers and crawlers.
"""


def exponential_backoff_delay(
    attempt: int, *, base_delay: float = 0.3, max_delay: float = 1.5
) -> float:
    """Calculate exponential backoff delay with a cap.

    Args:
        attempt: Current attempt number (0-indexed or 1-indexed)
        base_delay: Base delay multiplier in seconds (default: 0.3)
        max_delay: Maximum delay in seconds (default: 1.5)

    Returns:
        Delay in seconds, capped at max_delay

    Example:
        >>> exponential_backoff_delay(1)  # First retry
        0.3
        >>> exponential_backoff_delay(5)  # Fifth retry
        1.5
    """
    return min(base_delay * attempt, max_delay)
