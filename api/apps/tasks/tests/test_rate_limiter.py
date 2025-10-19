import asyncio
import time
from typing import List
from collections import deque

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from apps.tasks.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_allow_within_limit():
    rl = RateLimiter(max_requests=3, period_seconds=60)
    key = "user:1"

    assert await rl.allow(key) is True
    assert await rl.allow(key) is True
    assert await rl.allow(key) is True
    assert await rl.allow(key) is False  # 4th within window should be blocked


@pytest.mark.asyncio
async def test_isolated_per_key():
    rl = RateLimiter(max_requests=1, period_seconds=60)
    a, b = "A", "B"

    # A consumes its slot; B remains independent
    assert await rl.allow(a) is True
    assert await rl.allow(a) is False
    assert await rl.allow(b) is True


@pytest.mark.asyncio
async def test_concurrent_allow_respects_limit():
    """
    Launch a burst of allow() calls concurrently for the same key.
    Exactly max_requests should pass; the rest should be denied.
    """
    rl = RateLimiter(max_requests=5, period_seconds=2)
    key = "burst"

    async def try_once():
        return await rl.allow(key)

    results: List[bool] = await asyncio.gather(*(try_once() for _ in range(20)))
    assert sum(results) == 5
    assert results.count(False) == 15


@pytest.fixture
def client():
    app = FastAPI()
    app.state.rate_limiter = RateLimiter(max_requests=2, period_seconds=60)

    # Minimal dependency using RateLimiter stored on app.state
    async def enforce_rate_limit(request: Request):
        rl: RateLimiter = request.app.state.rate_limiter
        client = request.client.host if request.client else "unknown"
        allowed = await rl.allow(client)
        if not allowed:
            raise HTTPException(status_code=429, detail="Too Many Requests")

    @app.get("/ping", dependencies=[Depends(enforce_rate_limit)])
    async def ping():
        return {"ok": True}

    return TestClient(app)


def test_fastapi_integration_rate_limit(client: TestClient):
    r1 = client.get("/ping")
    r2 = client.get("/ping")
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Third should be rate-limited
    r3 = client.get("/ping")
    assert r3.status_code == 429
    assert r3.json()["detail"] == "Too Many Requests"


@pytest.mark.asyncio
async def test_cleanup_once_prunes_old_timestamps_and_empty_buckets():
    rl = RateLimiter(max_requests=10, period_seconds=1.0)
    now = time.monotonic()

    # 'old' completely expired -> bucket should be deleted
    rl._buckets["old"] = deque([now - 5.0, now - 2.0])

    # 'mixed' has some expired and some fresh -> only fresh should remain
    rl._buckets["mixed"] = deque([now - 2.0, now - 0.2])

    # 'fresh' entirely within window -> should be untouched
    rl._buckets["fresh"] = deque([now - 0.1, now - 0.05])

    await rl._cleanup_once()

    # 'old' removed entirely
    assert "old" not in rl._buckets

    # 'mixed' pruned to only non-expired items
    assert "mixed" in rl._buckets
    assert len(rl._buckets["mixed"]) == 1
    assert rl._buckets["mixed"][0] >= time.monotonic() - rl.period_seconds

    # 'fresh' stays
    assert "fresh" in rl._buckets
    assert len(rl._buckets["fresh"]) == 2
    assert all(ts >= time.monotonic() - rl.period_seconds for ts in rl._buckets["fresh"])


@pytest.mark.asyncio
async def test_allow_after_cleanup_allows_again():
    rl = RateLimiter(max_requests=1, period_seconds=0.1)
    key = "reset"

    # Consume the single slot
    assert await rl.allow(key) is True
    assert await rl.allow(key) is False

    # Age the timestamp to beyond the window and run one-off cleanup
    async with rl._lock:
        dq = rl._buckets[key]
        dq[0] = time.monotonic() - rl.period_seconds - 0.01

    await rl._cleanup_once()

    # Slot should be free again
    assert await rl.allow(key) is True


@pytest.mark.asyncio
async def test_background_cleanup_removes_expired_and_can_stop():
    # Very short periods so the test runs quickly
    rl = RateLimiter(max_requests=1, period_seconds=0.05, cleanup_interval=0.02)
    key = "bg"

    # Use up the slot
    assert await rl.allow(key) is True
    assert await rl.allow(key) is False

    # Age the entry so cleanup should remove it
    async with rl._lock:
        dq = rl._buckets[key]
        dq[0] = time.monotonic() - rl.period_seconds - 0.01

    # Start background cleanup and give it a moment to run
    await rl.start_cleanup()
    await asyncio.sleep(0.06)  # > cleanup_interval and roughly > one period

    # Should be allowed again because background cleanup pruned it
    assert await rl.allow(key) is True

    # Stop background task cleanly
    await rl.stop_cleanup()
    assert rl._cleanup_task is None
