"""Shared OCR helpers shared across modules and fallback engines."""

from __future__ import annotations

import base64
import io
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff"}


def _preprocess_for_ocr(raw: bytes) -> Image.Image:
    """Cheap, deterministic pre-processing that makes tesseract read phone
    photos of receipts (low-contrast, skew, small text) far more reliably.

    Grayscale -> upscale 2x -> Otsu binary threshold. No AI, no network, no
    model — just Pillow, so it runs in the gateway container offline.
    """
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw)).convert("L")
    img = ImageOps.autocontrast(img)
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
    # Otsu threshold to a clean black/white image.
    img = img.point(lambda p: 0 if p < 128 else 255)
    return img


def _tesseract_text(content_base64: str) -> str:
    """Local OCR via tesseract when no router and no pre-extracted text."""
    try:
        import pytesseract

        raw = base64.b64decode(content_base64)
        img = _preprocess_for_ocr(raw)
        return pytesseract.image_to_string(img, config="--psm 6")
    except Exception:
        return ""


def _extract_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
    return m.group(1) if m else None
