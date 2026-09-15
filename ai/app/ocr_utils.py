"""Shared OCR helpers shared across modules and fallback engines."""

from __future__ import annotations

import base64
import io
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff"}


def _otsu_threshold(histogram: list[int]) -> int:
    """Compute Otsu's optimal binarisation threshold from a 256-bin histogram.

    Maximises inter-class variance between foreground and background pixels.
    Falls back to 128 for degenerate (uniform) histograms.
    """
    total = sum(histogram)
    if total == 0:
        return 128
    sum_total = sum(i * histogram[i] for i in range(256))
    sum_bg = 0.0
    weight_bg = 0
    best_thresh = 128
    best_var = 0.0
    for t in range(256):
        weight_bg += histogram[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * histogram[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var = var
            best_thresh = t
    return best_thresh


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
    thresh = _otsu_threshold(img.histogram())
    img = img.point(lambda p: 0 if p < thresh else 255)
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
