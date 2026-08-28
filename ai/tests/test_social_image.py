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


@pytest.mark.asyncio
@pytest.mark.parametrize("dims", [
    (999999999, 999999999),
    (5000, 5000),
    (2048, 2048),   # exactly at cap — should pass through
    (0, 0),         # below min — clamped to 200
    (-100, -100),   # negative — clamped to 200
])
async def test_run_clamps_oversized_dimensions(dims) -> None:
    """AUT-1185 FINDING-01: width/height must be clamped to prevent OOM."""
    w, h = dims
    out = await run({"title": "Clamp", "width": w, "height": h})
    assert out["width"] == max(200, min(w, 2048))
    assert out["height"] == max(200, min(h, 2048))
    assert out["width"] <= 2048 and out["height"] <= 2048
    png = base64.b64decode(out["image_base64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_run_clamps_string_dimensions() -> None:
    """String dimensions (e.g. from JSON) must be coerced + clamped."""
    out = await run({"title": "Str", "width": "99999", "height": "99999"})
    assert out["width"] == 2048
    assert out["height"] == 2048

