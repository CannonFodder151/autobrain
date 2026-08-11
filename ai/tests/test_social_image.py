"""Tests for the social-image module (deterministic branded card path)."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import base64  # noqa: E402

import pytest  # noqa: E402

from app.modules.social_image import render_card, run  # noqa: E402


def test_render_card_produces_valid_png() -> None:
    png = render_card("SERVICE DUE IN 23 DAYS", "Your next service interval should feel like a pit stop.", "Download at autobrainservice.app")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_run_deterministic_default() -> None:
    out = await run({"title": "Test post", "hook": "A short hook", "cta": "Start free"})
    assert out["model"] == "rule-based-card"
    assert out["format"] == "png"
    assert out["width"] == 1200 and out["height"] == 630
    png = base64.b64decode(out["image_base64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
