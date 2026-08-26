"""CI webhook receiver (AUT-1669).

Receives GitHub Actions CI webhook pings from ci-triage-webhook.yml and
creates a child issue in Paperclip assigned to the CI Triage Agent.
Replaces the broken n8n webhook (trigger bb257f7977a59cbc8eef76ba).

Endpoint: POST /api/v1/ci/webhook
Auth:    Bearer token matching CI_TRIAGE_WEBHOOK_SECRET
"""

import hmac
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ci", tags=["ci"])

_BEARER_PREFIX = "bearer "


@router.post("/webhook")
async def ci_webhook(request: Request) -> dict:
    """Receive CI triage webhook from GitHub Actions and relay to Paperclip.

    Auth: Bearer token matching CI_TRIAGE_WEBHOOK_SECRET.
    Payload: {"event": "push", "repo": "owner/repo", "ref": "refs/heads/branch"}
    """
    if not settings.CI_TRIAGE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="CI triage webhook not configured")

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith(_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[len(_BEARER_PREFIX) :].strip()
    if not hmac.compare_digest(token, settings.CI_TRIAGE_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Invalid token")

    try:
        body = await request.json()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    repo = body.get("repo")
    ref = body.get("ref")
    if not repo or not ref:
        raise HTTPException(status_code=400, detail="Missing 'repo' or 'ref' in payload")

    logger.info("ci_webhook_received repo=%s ref=%s", repo, ref)

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
        logger.error("ci_webhook_paperclip_request_failed error=%s", exc)
        raise HTTPException(status_code=502, detail="Failed to reach Paperclip API")

    if resp.status_code >= 400:
        logger.error(
            "ci_webhook_paperclip_create_failed status=%d body=%s",
            resp.status_code,
            resp.text[:500],
        )
        raise HTTPException(status_code=502, detail="Failed to create Paperclip issue")

    try:
        created = resp.json()
    except (ValueError, TypeError):
        logger.error("ci_webhook_paperclip_non_json body=%s", resp.text[:500])
        raise HTTPException(status_code=502, detail="Paperclip API returned non-JSON response")

    logger.info("ci_webhook_child_created issue_id=%s", created.get("id"))
    return {"received": True, "issueId": created.get("id")}

