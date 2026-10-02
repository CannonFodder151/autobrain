"""CI webhook receiver (AUT-1669, AUT-3103).

Receives GitHub Actions CI webhook pings from ci-triage-webhook.yml and
creates a child issue in Paperclip assigned to the CI Triage Agent.

Endpoint: POST /api/v1/ci/webhook
Auth:    Bearer token matching CI_TRIAGE_WEBHOOK_SECRET

AUT-3103: Added strict rate limiting (per-IP), IP allowlist for known CI
providers (GitHub Actions), request fingerprint logging, and explicit
empty-string rejection for the secret.
"""

import hashlib
import hmac
import ipaddress
import logging
import secrets
import time

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ci", tags=["ci"])

_BEARER_PREFIX = "bearer "

# ---------- rate limiter (per-IP, Redis-backed) ----------

_CI_RATE_LIMIT_MAX = 10  # max requests per window per IP
_CI_RATE_WINDOW_SECONDS = 60  # 1-minute window


async def _ci_rate_bump(key: str, ttl: int) -> int:
    """INCR a key and return the count. Uses a direct Redis call to avoid
    importing the full rate_limit module (which pulls in auth dependencies)."""
    from redis.asyncio import Redis

    r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        return int(results[0])
    finally:
        await r.aclose()


def _client_ip(request: Request) -> str:
    """Extract client IP from request (nginx X-Real-IP or direct)."""
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def _ip_allowed(ip_str: str) -> bool:
    """Check if ip_str is in the CI_TRIAGE_ALLOWED_IPS allowlist."""
    allowed = settings.CI_TRIAGE_ALLOWED_IPS
    if not allowed:
        return True  # no allowlist configured → allow all
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        logger.warning("ci_webhook_invalid_client_ip ip=%s", ip_str)
        return False
    for entry in allowed.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def _request_fingerprint(request: Request, token: str) -> str:
    """SHA-256 fingerprint of client IP + token for audit logging."""
    raw = f"{_client_ip(request)}:{token}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@router.post("/webhook")
async def ci_webhook(request: Request) -> dict:
    """Receive CI triage webhook from GitHub Actions and relay to Paperclip.

    Auth: Bearer token matching CI_TRIAGE_WEBHOOK_SECRET.
    Payload: {"event": "push", "repo": "owner/repo", "ref": "refs/heads/branch"}

    AUT-3103: validates secret is non-empty, checks IP allowlist, enforces
    per-IP rate limit, and logs request fingerprint.
    """
    # --- 1. Reject empty secret explicitly ---
    if not settings.CI_TRIAGE_WEBHOOK_SECRET:
        logger.warning("ci_webhook_not_configured")
        raise HTTPException(status_code=503, detail="CI triage webhook not configured")

    # --- 2. Bearer token auth ---
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith(_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[len(_BEARER_PREFIX) :].strip()
    if not hmac.compare_digest(token, settings.CI_TRIAGE_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Invalid token")

    # --- 3. IP allowlist ---
    ip = _client_ip(request)
    if not _ip_allowed(ip):
        logger.warning("ci_webhook_ip_denied ip=%s", ip)
        raise HTTPException(status_code=403, detail="IP not allowed")

    # --- 4. Per-IP rate limit (fail-open) ---
    try:
        now_bucket = int(time.time()) // _CI_RATE_WINDOW_SECONDS
        rate_key = f"ci_webhook_rate:{ip}:{now_bucket}"
        count = await _ci_rate_bump(rate_key, _CI_RATE_WINDOW_SECONDS * 2)
        if count > _CI_RATE_LIMIT_MAX:
            logger.warning("ci_webhook_rate_limited ip=%s count=%d", ip, count)
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("ci_webhook_rate_limit_unavailable ip=%s error=%s", ip, exc)

    # --- 5. Parse body ---
    fp = _request_fingerprint(request, token)

    try:
        body = await request.json()
    except (ValueError, TypeError):
        logger.warning("ci_webhook_invalid_json fp=%s", fp)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    repo = body.get("repo")
    ref = body.get("ref")
    if not repo or not ref:
        logger.warning("ci_webhook_missing_fields fp=%s", fp)
        raise HTTPException(status_code=400, detail="Missing 'repo' or 'ref' in payload")

    logger.info("ci_webhook_received fp=%s repo=%s ref=%s", fp, repo, ref)

    # --- 6. Paperclip config check ---
    if not settings.PAPERCLIP_API_URL or not settings.PAPERCLIP_API_KEY:
        logger.error("ci_webhook_paperclip_not_configured")
        raise HTTPException(status_code=503, detail="Paperclip API not configured")

    if not settings.PAPERCLIP_COMPANY_ID or not settings.CI_TRIAGE_PARENT_ISSUE_ID or not settings.CI_TRIAGE_GOAL_ID:
        logger.error("ci_webhook_paperclip_incomplete_config")
        raise HTTPException(status_code=503, detail="Paperclip config incomplete")

    issue_url = f"{settings.PAPERCLIP_API_URL}/api/companies/{settings.PAPERCLIP_COMPANY_ID}/issues"
    payload = {
        "title": f"CI Triage: {repo} @ {ref.split('/')[-1]}",
        "description": (
            f"**Triggered by:** CI triage webhook\n"
            f"**Repository:** {repo}\n"
            f"**Ref:** {ref}\n\n"
            f"Review failed GitHub Actions runs for {repo} after push to {ref}."
        ),
        "parentId": settings.CI_TRIAGE_PARENT_ISSUE_ID,
        "goalId": settings.CI_TRIAGE_GOAL_ID,
        "assigneeAgentId": settings.CI_TRIAGE_AGENT_ID,
        "status": "todo",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                issue_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.PAPERCLIP_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        logger.error("ci_webhook_paperclip_request_failed fp=%s error=%s", fp, exc)
        raise HTTPException(status_code=502, detail="Failed to reach Paperclip API")

    if resp.status_code >= 400:
        logger.error(
            "ci_webhook_paperclip_create_failed fp=%s status=%d body=%s",
            fp,
            resp.status_code,
            resp.text[:500],
        )
        raise HTTPException(status_code=502, detail="Failed to create Paperclip issue")

    try:
        created = resp.json()
    except (ValueError, TypeError):
        logger.error("ci_webhook_paperclip_non_json fp=%s body=%s", fp, resp.text[:500])
        raise HTTPException(status_code=502, detail="Paperclip API returned non-JSON response")

    logger.info("ci_webhook_child_created fp=%s issue_id=%s", fp, created.get("id"))
    return {"received": True, "issueId": created.get("id")}
