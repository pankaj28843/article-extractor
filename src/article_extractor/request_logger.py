"""Request logging utilities for HTTP server middleware.

Provides consistent request/response logging with structured context,
eliminating duplication between success and failure logging paths.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def build_request_context(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    url_hint: str,
) -> dict[str, str | int | float]:
    """Build structured logging context for request completion.

    Args:
        request_id: Unique request identifier
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP response status code
        duration_ms: Request duration in milliseconds
        url_hint: Sanitized URL for logging

    Returns:
        Structured context dictionary for logging extra fields
    """
    return {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "url": url_hint,
    }


def compute_duration_ms(start_time: float) -> float:
    """Compute request duration in milliseconds from start time.

    Args:
        start_time: perf_counter value when request started

    Returns:
        Duration in milliseconds, rounded to 2 decimal places
    """
    return round((time.perf_counter() - start_time) * 1000, 2)


def log_request_failure(
    *,
    request_id: str,
    method: str,
    path: str,
    url_hint: str,
    start_time: float,
    status_code: int = 500,
) -> float:
    """Log request failure with structured context.

    Args:
        request_id: Unique request identifier
        method: HTTP method
        path: Request path
        url_hint: Sanitized URL for logging
        start_time: perf_counter when request started
        status_code: HTTP status code (default: 500)

    Returns:
        Duration in milliseconds (for metrics emission)
    """
    duration_ms = compute_duration_ms(start_time)
    context = build_request_context(
        request_id=request_id,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        url_hint=url_hint,
    )
    logger.exception("Request failed", extra=context)
    return duration_ms


def log_request_success(
    *,
    request_id: str,
    method: str,
    path: str,
    url_hint: str,
    start_time: float,
    status_code: int,
) -> float:
    """Log successful request completion with structured context.

    Args:
        request_id: Unique request identifier
        method: HTTP method
        path: Request path
        url_hint: Sanitized URL for logging
        start_time: perf_counter when request started
        status_code: HTTP response status code

    Returns:
        Duration in milliseconds (for metrics emission)
    """
    duration_ms = compute_duration_ms(start_time)
    context = build_request_context(
        request_id=request_id,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        url_hint=url_hint,
    )
    logger.info("Request complete", extra=context)
    return duration_ms
