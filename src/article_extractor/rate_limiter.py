"""Adaptive rate limiting for polite web crawling.

Provides per-host rate limiting with automatic backoff when rate limits
are encountered (429 responses). Tracks state per host and adjusts delays
dynamically based on success/failure patterns.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class RateLimitEvent:
    """Tracks a rate limit event for adaptive backoff."""

    timestamp: float
    host: str
    status_code: int
    was_success: bool


@dataclass
class HostRateLimitState:
    """Tracks rate limiting state for a specific host."""

    host: str
    base_delay: float = 2.0
    current_delay: float = 2.0
    min_delay: float = 0.5
    max_delay: float = 120.0
    consecutive_429s: int = 0
    consecutive_successes: int = 0
    total_429s: int = 0
    total_requests: int = 0
    last_429_time: float = 0.0
    events: deque = field(default_factory=lambda: deque(maxlen=100))

    def record_success(self) -> None:
        self.consecutive_429s = 0
        self.consecutive_successes += 1
        self.total_requests += 1
        self.events.append(
            RateLimitEvent(
                timestamp=time.time(),
                host=self.host,
                status_code=200,
                was_success=True,
            )
        )

        if self.consecutive_successes >= 10:
            self.current_delay = max(self.min_delay, self.current_delay * 0.9)
            self.consecutive_successes = 0
            logger.debug(
                "[%s] Reduced delay to %.2fs after successful streak",
                self.host,
                self.current_delay,
            )

    def record_429(self) -> None:
        now = time.time()
        self.consecutive_successes = 0
        self.consecutive_429s += 1
        self.total_429s += 1
        self.total_requests += 1
        self.events.append(
            RateLimitEvent(
                timestamp=now,
                host=self.host,
                status_code=429,
                was_success=False,
            )
        )

        time_since_last_429 = (
            now - self.last_429_time if self.last_429_time > 0 else float("inf")
        )
        self.last_429_time = now

        if time_since_last_429 < 30:
            multiplier = 2.0
        elif time_since_last_429 < 60:
            multiplier = 1.5
        else:
            multiplier = 1.25

        if self.consecutive_429s >= 3:
            multiplier *= 1.5

        old_delay = self.current_delay
        self.current_delay = min(self.max_delay, self.current_delay * multiplier)

        logger.warning(
            "[%s] 429 received! Delay: %.2fs -> %.2fs (consecutive: %s, total: %s, time_since_last: %.1fs)",
            self.host,
            old_delay,
            self.current_delay,
            self.consecutive_429s,
            self.total_429s,
            time_since_last_429,
        )

    def get_recent_429_rate(self, window_seconds: float = 300) -> float:
        now = time.time()
        cutoff = now - window_seconds
        recent_events = [e for e in self.events if e.timestamp > cutoff]
        if not recent_events:
            return 0.0
        rate_limit_events = [e for e in recent_events if e.status_code == 429]
        return len(rate_limit_events) / len(recent_events)

    def get_delay(self) -> float:
        import secrets

        rng = secrets.SystemRandom()
        jitter = rng.uniform(0.8, 1.2)
        return self.current_delay * jitter


class AdaptiveRateLimiter:
    """Manages per-host adaptive rate limiting."""

    def __init__(self, default_delay: float = 2.0):
        self.default_delay = default_delay
        self._host_states: dict[str, HostRateLimitState] = {}
        self._lock = asyncio.Lock()

    def _get_host_state(self, host: str) -> HostRateLimitState:
        if host not in self._host_states:
            self._host_states[host] = HostRateLimitState(
                host=host,
                base_delay=self.default_delay,
                current_delay=self.default_delay,
            )
        return self._host_states[host]

    def record_success(self, url: str) -> None:
        host = urlparse(url).netloc
        state = self._get_host_state(host)
        state.record_success()

    def record_429(self, url: str) -> None:
        host = urlparse(url).netloc
        state = self._get_host_state(host)
        state.record_429()

    def get_delay(self, url: str) -> float:
        host = urlparse(url).netloc
        state = self._get_host_state(host)
        return state.get_delay()

    async def wait(self, url: str, last_request_time: float) -> float:
        async with self._lock:
            current_time = time.time()
            delay = self.get_delay(url)
            time_since_last = current_time - last_request_time

            if time_since_last < delay:
                sleep_time = delay - time_since_last
                logger.debug(
                    "Rate limiting: sleeping for %.2fs (adaptive delay: %.2fs)",
                    sleep_time,
                    delay,
                )
                await asyncio.sleep(sleep_time)

            return time.time()

    def get_stats(self) -> dict[str, dict[str, float]]:
        return {
            host: {
                "current_delay": state.current_delay,
                "total_429s": state.total_429s,
                "total_requests": state.total_requests,
                "recent_429_rate": state.get_recent_429_rate(),
            }
            for host, state in self._host_states.items()
        }
