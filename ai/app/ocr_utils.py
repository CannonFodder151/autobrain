"""Shared OCR helpers shared across modules and fallback engines."""

import base64
import io
import re

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/tiff"}


def _tesseract_text(content_base64: str) -> str:
    """Local OCR via tesseract when no router and no pre-extracted text."""
    try:
        import pytesseract
        from PIL import Image

        raw = base64.b64decode(content_base64)
        return pytesseract.image_to_string(Image.open(io.BytesIO(raw)))
    except Exception:
        return ""


def _extract_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
    return m.group(1) if m else None
