import asyncio
import time
import logging
from collections import deque
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    
    def __init__(
            self, max_requests: int,
            period_seconds: float = 60,
            cleanup_interval: float = 300
    ) -> None:
        self.max_requests = int(max_requests)
        self.period_seconds = float(period_seconds)
        self.cleanup_interval = float(cleanup_interval)
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup(self):
        """Start periodic cleanup in the background."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self):
        """Stop the cleanup task gracefully."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        logger.info("Starting rate-limiter cleanup task")
        while True:
            await asyncio.sleep(self.cleanup_interval)
            await self._cleanup_once()

    async def _cleanup_once(self):
        now = time.monotonic()
        cutoff = now - self.period_seconds
        async with self._lock:
            for key in list(self._buckets.keys()):
                dq = self._buckets[key]
                # drop expired timestamps
                while dq and dq[0] < cutoff:
                    dq.popleft()
                # drop empty buckets entirely
                if not dq:
                    del self._buckets[key]

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.period_seconds
        async with self._lock:
            dq = self._buckets.setdefault(key, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True

    async def remaining(self, key: str) -> int:
        now = time.monotonic()
        cutoff = now - self.period_seconds
        async with self._lock:
            dq = self._buckets.get(key, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            return max(0, self.max_requests - len(dq))

    async def reset(self, key: Optional[str] = None) -> None:
        async with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
