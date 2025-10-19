import asyncio
from typing import List

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
async def test_remaining_and_window_expiry():
    # Use a short window so the test runs fast and stable
    rl = RateLimiter(max_requests=2, period_seconds=1)
    key = "user:2"

    # Initially 2 remaining
    assert await rl.remaining(key) == 2
    assert await rl.allow(key) is True
    assert await rl.remaining(key) == 1
    assert await rl.allow(key) is True
    assert await rl.remaining(key) == 0
    assert await rl.allow(key) is False

    # After the window passes, counters should roll off
    await asyncio.sleep(1)
    assert await rl.allow(key) is True
    assert await rl.remaining(key) == 1


@pytest.mark.asyncio
async def test_isolated_per_key():
    rl = RateLimiter(max_requests=1, period_seconds=60)
    a, b = "A", "B"

    # A consumes its slot; B remains independent
    assert await rl.allow(a) is True
    assert await rl.allow(a) is False
    assert await rl.allow(b) is True


@pytest.mark.asyncio
async def test_reset_key_and_reset_all():
    rl = RateLimiter(max_requests=2, period_seconds=60)
    k1, k2 = "K1", "K2"

    await rl.allow(k1)
    await rl.allow(k2)
    await rl.allow(k2)
    assert await rl.remaining(k1) == 1
    assert await rl.remaining(k2) == 0

    # Reset K2 only
    await rl.reset(k2)
    assert await rl.remaining(k2) == 2
    # K1 unchanged
    assert await rl.remaining(k1) == 1

    # Reset all
    await rl.reset()
    assert await rl.remaining(k1) == 2
    assert await rl.remaining(k2) == 2


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
    # Remaining should be 0
    assert await rl.remaining(key) == 0


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
