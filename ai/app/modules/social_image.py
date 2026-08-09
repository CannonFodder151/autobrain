"""AI module: social post image generation (LinkedIn + Facebook).

Deterministic-first: renders an on-brand AutoBrain card (headline, hook,
CTA on the brand palette) with Pillow. Zero external dependencies, always
available, free — matching the company rule of "deterministic paths first,
AI fallback". The AI path (free Pollinations text-to-image) is used only
when the caller explicitly asks for a photoreal/illustrative image, and the
deterministic card is the fallback if the AI call fails.

Input:  title, hook, cta (optional), prompt (optional, AI mode),
        width/height (optional, default 1200x630 — suits both LinkedIn and
        Facebook feed posts).
Output: image_base64 (PNG), width, height, format, model.
"""

import base64
import io

import httpx
from PIL import Image, ImageDraw, ImageFont

_BRAND_TEAL = (13, 148, 136)
_BRAND_CHARCOAL = (23, 28, 33)
_BRAND_GOLD = (212, 165, 60)
_BRAND_WHITE = (255, 255, 255)
_BRAND_LIGHT = (234, 240, 240)

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default(size)


def _wrap(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.getbbox(candidate)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_card(
    title: str,
    hook: str = "",
    cta: str = "",
    width: int = 1200,
    height: int = 630,
) -> bytes:
    """Deterministic branded card. Always succeeds, never touches the network."""
    img = Image.new("RGB", (width, height), _BRAND_CHARCOAL)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 10], fill=_BRAND_TEAL)
    title_font = _load_font(int(height * 0.10))
    hook_font = _load_font(int(height * 0.052))
    cta_font = _load_font(int(height * 0.045))

    margin = int(width * 0.08)
    y = int(height * 0.10)
    lines = _wrap(title.upper(), title_font, width - 2 * margin)
    for line in lines[:4]:
        draw.text((margin, y), line, font=title_font, fill=_BRAND_TEAL)
        y += int(height * 0.115)

    if hook:
        y += int(height * 0.04)
        for line in _wrap(hook, hook_font, width - 2 * margin)[:3]:
            draw.text((margin, y), line, font=hook_font, fill=_BRAND_LIGHT)
            y += int(height * 0.075)

    if cta:
        y = height - int(height * 0.12)
        draw.rectangle([margin, y - int(height * 0.02), margin + draw.textbbox((0, 0), cta, font=cta_font)[2] + int(width * 0.02), y + int(height * 0.05)], fill=_BRAND_TEAL)
        draw.text((margin + int(width * 0.01), y), cta, font=cta_font, fill=_BRAND_WHITE)

    draw.text((margin, height - int(height * 0.055)), "AutoBrain", font=_load_font(int(height * 0.04)), fill=_BRAND_GOLD)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _ai_image(prompt: str, width: int, height: int) -> bytes | None:
    """Free Pollinations text-to-image. Returns PNG bytes or None on any failure."""
    url = (
        "https://image.pollinations.ai/prompt/"
        + prompt.replace(" ", "%20").replace(",", "%2C")
        + f"?width={width}&height={height}&nologo=true"
    )
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception:
        return None


async def run(payload: dict) -> dict:
    width = int(payload.get("width", 1200))
    height = int(payload.get("height", 630))
    title = str(payload.get("title") or "AutoBrain").strip()
    hook = str(payload.get("hook") or "").strip()
    cta = str(payload.get("cta") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()

    if prompt and len(prompt) > 8:
        png = await _ai_image(prompt, width, height)
        if png:
            return {
                "image_base64": base64.b64encode(png).decode(),
                "width": width,
                "height": height,
                "format": "png",
                "model": "pollinations-ai",
            }

    png = render_card(title, hook, cta, width, height)
    return {
        "image_base64": base64.b64encode(png).decode(),
        "width": width,
        "height": height,
        "format": "png",
        "model": "rule-based-card",
    }
