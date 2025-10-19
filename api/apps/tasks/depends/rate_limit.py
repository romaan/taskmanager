from fastapi import HTTPException, Request

async def enforce_rate_limit(request: Request) -> None:
    rl = request.app.state.rate_limiter
    key = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
           or (request.client.host if request.client else "unknown"))
    if not await rl.allow(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded (max requests/min).")
