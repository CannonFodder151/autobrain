"""FastAPI dependency functions for rate limiting.

Thin wrappers around the pure rate-limit logic in ``services.rate_limit``.
This file owns the FastAPI ``Depends`` integration so the service layer stays
framework-free. API routers import from here, never from services.rate_limit
directly for dependency injection.
"""

from fastapi import Depends, HTTPException

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.models.user import User
from app.services.rate_limit import (
    _bump_ai,
    _bump_rego,
)

logger = get_logger(__name__)


async def require_ai_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Reject the request with 429 when the user is over their AI budget.

    Counting here (not per-AI-module) keeps one shared budget per account so a
    user cannot dodge the cap by rotating between features.

    Fail-closed: Redis failure returns 503.
    """
    from app.core.config import settings

    burst, day = await _bump_ai(user.id)
    if burst > settings.AI_RATE_LIMIT_PER_WINDOW or day > settings.AI_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="AI request limit reached. Try again later.",
            headers={"Retry-After": str(settings.AI_RATE_WINDOW_SECONDS)},
        )
    return user


async def require_ai_rate_limit_best_effort(
    user: User = Depends(get_current_user),
) -> User:
    """Like ``require_ai_rate_limit`` but fail-OPEN when Redis is unreachable.

    Used by endpoints whose core operation is deterministic (storing an uploaded
    receipt / running the local tesseract+rule OCR path). A Redis blip must not
    drop that work — only the 9Router enrichment is AI-spend, and ``enhance``
    already falls back to the baseline when the router is down.
    """
    from app.core.config import settings

    burst, day = await _bump_ai(user.id)
    if burst > settings.AI_RATE_LIMIT_PER_WINDOW or day > settings.AI_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="AI request limit reached. Try again later.",
            headers={"Retry-After": str(settings.AI_RATE_WINDOW_SECONDS)},
        )
    return user


async def require_rego_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Reject with 429 when the user exceeds the rego-lookup hourly cap.

    Fail-open: if Redis is unreachable the request proceeds with a warning
    rather than blocking a non-cost-critical lookup.
    """
    from app.core.config import settings

    now, count = await _bump_rego(user.id)
    if count > settings.REGO_RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Rego lookup limit reached ({settings.REGO_RATE_LIMIT_PER_HOUR}/hour). Try again later.",
            headers={"Retry-After": str(settings.REGO_RATE_WINDOW_SECONDS - (now % settings.REGO_RATE_WINDOW_SECONDS))},
        )
    return user
