import asyncio
import time
from collections import deque
from typing import Deque, Dict, Optional


class RateLimiter:
    """
    Simple in-memory sliding-window rate limiter.
    - Per key (e.g., client IP), allow at most `max_requests` within `period_seconds`.
    - Uses asyncio.Lock for concurrency safety in a single-process async server.
    """
    def __init__(self, max_requests: int, period_seconds: float = 60) -> None:
        self.max_requests = int(max_requests)
        self.period_seconds = float(period_seconds)
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        """
        Returns True if this request is allowed, False if rate-limited.
        """
        now = time.monotonic()
        cutoff = now - self.period_seconds
        async with self._lock:
            dq = self._buckets.setdefault(key, deque())
            # drop timestamps older than the window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True

    async def remaining(self, key: str) -> int:
        """
        Best-effort remaining count in the current window (non-atomic).
        """
        now = time.monotonic()
        cutoff = now - self.period_seconds
        async with self._lock:
            dq = self._buckets.get(key, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            return max(0, self.max_requests - len(dq))

    async def reset(self, key: Optional[str] = None) -> None:
        """
        Clear counters. If `key` is None, reset all buckets.
        """
        async with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
