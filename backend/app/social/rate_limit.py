"""Per-client social route rate limiting (MB-1/MB-2, AUT-462).

In-process sliding window keyed by (route path, client IP). Exceeding the
limit returns 429 with a `Retry-After` header. Deterministic, no AI.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class _SlidingWindow:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, key: tuple[str, str], limit: int) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > WINDOW_SECONDS:
            q.popleft()
        if len(q) >= limit:
            retry_after = max(1, int(WINDOW_SECONDS - (now - q[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Slow down and try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)


_window = _SlidingWindow()


def social_rate_limit(limit: int):
    """Dependency factory: enforce `limit` requests per 60s window per client IP."""

    def _dep(request: Request) -> None:
        _window.check((request.url.path, client_ip(request)), limit)

    return _dep
