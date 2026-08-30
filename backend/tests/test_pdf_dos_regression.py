"""Regression guard for AUT-471: crafted-PDF DoS against the receipt worker.

Covers the two pypdf CVEs fixed in 6.15.0:
- GHSA-fp3f-mc75-235c: large /ToUnicode CMap streams -> high memory.
- GHSA-fwg2-594c-jp42: oversized CID font width ranges -> long runtime/memory.

Attacker-controlled receipt PDFs hit `_pdf_text()` in
`app/workers/tasks.py` (untrusted uploads), so pypdf must reject both shapes
fast instead of expanding them. A vulnerable pypdf parses the width-range PDF
to real text; 6.15.0+ rejects it (LimitReachedError -> worker returns "").
"""

import io
import time

from app.workers.tasks import _pdf_text

LARGE_TO_UNICODE_CMAP = b"""\
/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
2 beginbfrange
<0000> <FFFF> <0000>
<0000> <FFFF> <0000>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""

REJECT_BOUND_S = 5.0


def _build_pdf(cid_width_range: str | None, to_unicode_cmap: bytes | None) -> bytes:
    """Hand-built 7-object PDF: page -> Type0 font (-> CID font -> optional /ToUnicode)."""
    tu_len = len(to_unicode_cmap) if to_unicode_cmap else 0
    font = (
        "<< /Type /Font /Subtype /Type0 /BaseFont /Arial /Encoding /Identity-H "
        "/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>"
        if to_unicode_cmap
        else "<< /Type /Font /Subtype /Type0 /BaseFont /Arial /Encoding /Identity-H "
        "/DescendantFonts [6 0 R] >>"
    )
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        "<< /Length 44 >> stream\nBT /F1 12 Tf 72 720 Td (Test) Tj ET\nendstream",
        font,
        "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Arial "
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/W [{cid_width_range}] >>",
        f"<< /Length {tu_len} >> stream\n".encode()
        + (to_unicode_cmap if to_unicode_cmap is not None else b"")
        + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [out.tell()]
    for i, obj in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj {obj}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def test_oversized_cid_width_range_rejected_fast() -> None:
    data = _build_pdf(cid_width_range="0 70000 500", to_unicode_cmap=None)
    start = time.monotonic()
    text = _pdf_text(data)
    elapsed = time.monotonic() - start
    assert text == "", (
        "oversized /W range parsed to text instead of being rejected; "
        "pypdf < 6.15.0 re-exposes GHSA-fwg2-594c-jp42 (AUT-471)"
    )
    assert elapsed < REJECT_BOUND_S, f"oversized /W range took {elapsed:.2f}s"


def test_large_to_unicode_stream_rejected_fast() -> None:
    data = _build_pdf(cid_width_range="0 500 500", to_unicode_cmap=LARGE_TO_UNICODE_CMAP)
    start = time.monotonic()
    text = _pdf_text(data)
    elapsed = time.monotonic() - start
    assert text == "", (
        "large /ToUnicode stream parsed instead of being rejected; "
        "re-exposes GHSA-fp3f-mc75-235c (AUT-471)"
    )
    assert elapsed < REJECT_BOUND_S, f"large /ToUnicode stream took {elapsed:.2f}s"
