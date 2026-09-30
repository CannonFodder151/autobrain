"""Regression guard for AUT-794: transitive CVE pins (starlette, ecdsa).

The resolved tree used to ship starlette 0.41.3 (via fastapi) and ecdsa 0.19.2
(via python-jose), both with known CVEs that the `--no-deps` pip-audit gate
cannot see. Requirements must stay on a fastapi/starlette combo at/above the
fixes and must NOT pull python-jose/ecdsa back in. The weekly full-resolution
scan (`.github/workflows/security-scan.yml`) catches the runtime reality; this
test locks the pins deterministically.
"""

from pathlib import Path

REQ_FILES = [
    Path(__file__).resolve().parents[1] / "requirements.txt",
    Path(__file__).resolve().parents[2] / "ai" / "requirements.txt",
]

MIN_FASTAPI = (0, 133, 0)  # first fastapi without a starlette upper bound
MIN_STARLETTE = (1, 3, 1)  # clears all 7 starlette PYSEC-2026 entries


def _pins(req_file: Path) -> dict[str, tuple[int, ...]]:
    pins: dict[str, tuple[int, ...]] = {}
    for line in req_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, version = line.partition("==")
        # Drop extras: `PyJWT[crypto]` keys as `pyjwt`.
        name = name.partition("[")[0].strip()
        # Only the leading numeric segments are comparable; PEP 440 suffixes
        # (`2.9.0.post0`) previously raised ValueError and broke the whole file.
        parts: list[int] = []
        for segment in version.split("."):
            if not segment.isdigit():
                break
            parts.append(int(segment))
        if name and parts:
            pins[name.lower()] = tuple(parts)
    return pins


def test_fastapi_and_starlette_above_cve_fixes() -> None:
    for req_file in REQ_FILES:
        pins = _pins(req_file)
        fastapi = pins.get("fastapi")
        starlette = pins.get("starlette")
        assert fastapi is not None, f"{req_file.name}: missing fastapi pin"
        assert starlette is not None, f"{req_file.name}: missing starlette pin"
        assert fastapi >= MIN_FASTAPI, (
            f"{req_file.name}: fastapi {fastapi} < {MIN_FASTAPI} re-allows "
            "starlette <1.3.1 (starlette PYSEC-2026-161/248/249/1942/1941/2281/2280)"
        )
        assert starlette >= MIN_STARLETTE, (
            f"{req_file.name}: starlette {starlette} < {MIN_STARLETTE} "
            "re-exposes the starlette PYSEC-2026 CVE set (AUT-794)"
        )


def test_pyjwt_replaces_python_jose_and_ecdsa() -> None:
    pins = _pins(REQ_FILES[0])
    assert pins.get("pyjwt") is not None, "backend must pin PyJWT[crypto]"
    assert "python-jose" not in pins and "ecdsa" not in pins, (
        "python-jose/ecdsa must not be reintroduced: ecdsa 0.19.2 (the latest "
        "published) carries PYSEC-2026-1325 and python-jose is unmaintained"
    )

# AUT-4701: PyJWT 2.13.0 carried 12 OSV advisories. 2.14.0 fixes 11 but leaves
# GHSA-42vr-xj54-vc7v (unauthenticated RecursionError DoS reachable through
# PyJWKClient.get_signing_key_from_jwt with verify_signature=False, fixed in
# 2.15.0), so the floor is 2.15.0 — not 2.14.0.
MIN_PYJWT = (2, 15, 0)


def test_pyjwt_above_cve_fixes() -> None:
    pyjwt = _pins(REQ_FILES[0]).get("pyjwt")
    assert pyjwt is not None, "backend must pin PyJWT[crypto]"
    assert pyjwt >= MIN_PYJWT, (
        f"backend: pyjwt {'.'.join(map(str, pyjwt))} < {'.'.join(map(str, MIN_PYJWT))} "
        "re-exposes the PyJWT GHSA set, including GHSA-42vr-xj54-vc7v "
        "(pre-verification recursion DoS) which 2.14.0 does NOT fix (AUT-4701)"
    )
