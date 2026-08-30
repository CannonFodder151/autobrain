"""Per-client social route rate limiting (MB-1/MB-2, AUT-462).

In-process sliding window keyed by (route path, client IP). Exceeding the
limit returns 429 with a `Retry-After` header. Deterministic, no AI.
"""

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from app.api.deps import require_premium_write
from app.services.auth import client_ip

WINDOW_SECONDS = 60


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
_user_window = _SlidingWindow()


def social_rate_limit(limit: int):
    """Dependency factory: enforce `limit` requests per 60s window per client IP."""

    def _dep(request: Request) -> None:
        _window.check((request.url.path, client_ip(request)), limit)

    return _dep


def social_user_rate_limit(scope: str, limit: int):
    """Dependency factory: enforce `limit` requests per 60s window per user.

    Per-user caps (e.g. flags capped per user per window) where per-IP limits
    would miss an authenticated attacker rotating through resources.
    """

    def _dep(user=Depends(require_premium_write)) -> None:
        _user_window.check((scope, user.id), limit)

    return _dep
