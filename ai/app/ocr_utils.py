"""Shared OCR helpers shared across modules and fallback engines."""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff"}


def _preprocess_for_ocr(raw: bytes) -> Image.Image:
    """Cheap, deterministic pre-processing that makes tesseract read phone
    photos of receipts (low-contrast, skew, small text) far more reliably.

    Grayscale -> autocontrast -> upscale 2x -> adaptive threshold.
    No AI, no network, no model — just Pillow, so it runs in the gateway
    container offline.
    """
    from PIL import Image, ImageFilter, ImageOps

    img = Image.open(io.BytesIO(raw)).convert("L")
    img = ImageOps.autocontrast(img)
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
    # Median filter removes salt-and-pepper noise from phone photos.
    img = img.filter(ImageFilter.MedianFilter(size=3))
    # Adaptive threshold: use the image mean as the cut-off instead of a
    # fixed 128, which washes out text on dark receipts or underexposed
    # phone photos. Histogram is O(palette) not O(pixels).
    hist = img.histogram()
    total_pixels = sum(hist)
    total_sum = sum(i * c for i, c in enumerate(hist))
    threshold = total_sum // total_pixels if total_pixels else 128
    img = img.point(lambda p: 0 if p < threshold else 255)
    return img


def _tesseract_text(content_base64: str) -> str:
    """Local OCR via tesseract when no router and no pre-extracted text."""
    try:
        import pytesseract

        raw = base64.b64decode(content_base64)
        img = _preprocess_for_ocr(raw)
        text = pytesseract.image_to_string(img, config="--psm 6")
        if not text.strip():
            logger.warning("tesseract_returned_empty_text")
        return text
    except ImportError:
        logger.warning("pytesseract_not_installed")
        return ""
    except Exception:
        logger.exception("tesseract_ocr_failed")
        return ""


def _extract_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
    return m.group(1) if m else None
