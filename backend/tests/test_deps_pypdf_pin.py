"""Regression guard for AUT-301: pypdf pin must stay on the CVE-2026-71852/71870 fix.

Both runtime requirement files must resolve pypdf to >= 6.15.0. If a future
bump (or accidental downgrade) drops it below, the crafted-PDF DoS the Celery
receipt worker's `_pdf_text()` is exposed to comes back.
"""

from pathlib import Path

REQ_FILES = [
    Path(__file__).resolve().parents[1] / "requirements.txt",
    Path(__file__).resolve().parents[2] / "ai" / "requirements.txt",
]

MIN_PYPDF = (6, 15, 0)


def _pypdf_pin(req_file: Path) -> tuple[int, ...]:
    for line in req_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, version = line.partition("==")
        if name.strip() == "pypdf":
            return tuple(int(part) for part in version.split("."))
    raise AssertionError(f"pypdf pin missing from {req_file}")


def test_pypdf_pinned_above_cve_fix() -> None:
    for req_file in REQ_FILES:
        pin = _pypdf_pin(req_file)
        assert pin >= MIN_PYPDF, (
            f"{req_file.name}: pypdf {pin} is < 6.15.0, "
            "re-exposes CVE-2026-71852/CVE-2026-71870 (AUT-301)"
        )
