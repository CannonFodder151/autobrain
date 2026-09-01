"""Tests for the social-image module (deterministic branded card path)."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import base64  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.modules.social_image import (  # noqa: E402
    _MAX_PROMPT_LEN,
    render_card,
    run,
)


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


@pytest.mark.asyncio
async def test_ai_image_rejects_overlong_prompt() -> None:
    """AUT-1604: Prompt exceeding MAX_PROMPT_LEN must be rejected."""
    from app.modules.social_image import _ai_image
    long_prompt = "a" * (_MAX_PROMPT_LEN + 1)
    result = await _ai_image(long_prompt, 1200, 630)
    assert result is None


@pytest.mark.asyncio
async def test_ai_image_url_encodes_injection_chars() -> None:
    """AUT-1604: URL injection characters must be percent-encoded."""
    from app.modules.social_image import _ai_image
    with patch("app.modules.social_image.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.content = b"fake-png-bytes"
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        prompt = "car?width=9999&height=9999#frag"
        await _ai_image(prompt, 1200, 630)

        called_url = mock_client.return_value.__aenter__.return_value.get.call_args[0][0]
        assert "car%3Fwidth%3D9999%26height%3D9999%23frag" in called_url
        assert "width=9999&" not in called_url or called_url.count("width=") == 1
        assert "height=9999" not in called_url or called_url.count("height=") == 1


@pytest.mark.asyncio
async def test_ai_image_blocks_path_traversal() -> None:
    """AUT-1604: Path traversal sequences must be encoded."""
    from app.modules.social_image import _ai_image
    with patch("app.modules.social_image.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.content = b"fake-png-bytes"
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        prompt = "x/../v1/other-endpoint"
        await _ai_image(prompt, 1200, 630)

        called_url = mock_client.return_value.__aenter__.return_value.get.call_args[0][0]
        assert "x%2F..%2Fv1%2Fother-endpoint" in called_url
        assert "/../" not in called_url


@pytest.mark.asyncio
async def test_ai_image_blocks_fragment_injection() -> None:
    """AUT-1604: Fragment (#) must be encoded, not truncate query."""
    from app.modules.social_image import _ai_image
    with patch("app.modules.social_image.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.content = b"fake-png-bytes"
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)

        prompt = "car#"
        await _ai_image(prompt, 1200, 630)

        called_url = mock_client.return_value.__aenter__.return_value.get.call_args[0][0]
        assert "car%23" in called_url
        assert called_url.count("?") == 1

