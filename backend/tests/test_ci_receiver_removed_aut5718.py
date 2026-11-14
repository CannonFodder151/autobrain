"""AUT-5718: the dead POST /api/v1/ci/webhook receiver must stay gone.

CI triage is woken by the Paperclip routine trigger that
.github/workflows/ci-triage-webhook.yml fires, never by this backend. If
/api/v1/ci/webhook reappears it is a second, competing receiver that will
answer 503 in every environment (AUT-5694). Fail CI instead.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_ci_webhook_route_is_not_registered() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/ci/webhook", json={"repo": "o/r", "ref": "refs/heads/main"})
    assert resp.status_code == 404, f"/ci/webhook is live again (HTTP {resp.status_code})"


def test_ci_triage_settings_are_gone() -> None:
    fields = Settings.model_fields
    for name in (
        "CI_TRIAGE_WEBHOOK_SECRET",
        "CI_TRIAGE_PARENT_ISSUE_ID",
        "CI_TRIAGE_GOAL_ID",
        "CI_TRIAGE_AGENT_ID",
    ):
        assert name not in fields, f"{name} is back in Settings"