"""Adaptive concurrency limiting for async workers.

Provides dynamic concurrency control that automatically adjusts worker
limits based on success/failure patterns. Increases concurrency during
successful operations and decreases when rate limits are hit.
"""

from __future__ import annotations

import asyncio
import time


class AdaptiveConcurrencyLimiter:
    """Dynamically adjusts crawler worker concurrency based on host feedback."""

    def __init__(self, min_limit: int, max_limit: int):
        self._min_limit = max(1, min_limit)
        self._max_limit = max(self._min_limit, max_limit)
        self._limit = self._min_limit
        self._peak_limit = self._limit
        self._active = 0
        self._peak_active = 0
        self._success_streak = 0
        self._last_rate_limit_at = 0.0
        self._condition = asyncio.Condition()

    async def acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self._active < self._limit)
            self._active += 1
            self._peak_active = max(self._peak_active, self._active)

    async def release(self) -> None:
        async with self._condition:
            self._active = max(0, self._active - 1)
            self._condition.notify_all()

    async def record_success(self) -> None:
        async with self._condition:
            self._success_streak += 1
            window_clear = (time.time() - self._last_rate_limit_at) >= 60
            if (
                self._limit < self._max_limit
                and self._success_streak >= 25
                and window_clear
            ):
                self._limit += 1
                self._peak_limit = max(self._peak_limit, self._limit)
                self._success_streak = 0
                self._condition.notify_all()

    async def record_rate_limit(self) -> None:
        async with self._condition:
            new_limit = max(self._min_limit, self._limit // 2)
            self._limit = min(self._limit, new_limit)
            self._success_streak = 0
            self._last_rate_limit_at = time.time()
            self._condition.notify_all()

    def snapshot(self) -> dict[str, int]:
        return {
            "current_limit": self._limit,
            "peak_limit": self._peak_limit,
            "active_workers": self._active,
            "peak_active": self._peak_active,
        }
