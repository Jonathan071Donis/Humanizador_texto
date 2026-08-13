"""
Simple in-memory rate limiting: max N requests per minute per client IP.
No external store (redis, etc) - a dict is enough for a single-process
demo deployment.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
WINDOW_SECONDS = 60

_hits: Dict[str, Deque[float]] = defaultdict(deque)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Health checks and static assets are exempt.
        if request.url.path in ("/health", "/favicon.ico") or request.url.path.startswith("/static"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = _hits[client_ip]

        while window and now - window[0] > WINDOW_SECONDS:
            window.popleft()

        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: max {RATE_LIMIT_PER_MINUTE} requests/minute."},
            )

        window.append(now)
        return await call_next(request)
