#!/usr/bin/env python3
"""AUT-4718 self-check: the trivy base-image gate must scan what we actually build.

The gate was red on `main` for a week because three nginx pins had drifted onto
three different digests, and the python base had accumulated unshipped-fix CVEs.
This asserts the invariants that let a reviewer trust a red/green `image-scan`:
every base-image pin is digest-pinned, the Dockerfile pins and the scan env agree,
and no `.trivyignore` entry is dead (a suppression for a CVE the pinned image no
longer reports hides the next real finding).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Which Dockerfile pins which image. `pgvector` is not in a Dockerfile (compose
# only), so it is checked against the scan env directly.
PYTHON_DOCKERFILES = [
    "docker/backend/Dockerfile",
    "docker/ai/Dockerfile",
    "docker/worker/Dockerfile",
    "market-data/Dockerfile",
]
NGINX_DOCKERFILE = "docker/frontend/Dockerfile"
SCAN_WORKFLOW = ".github/workflows/trivy-image-scan.yml"
EXPAT_WORKFLOW = ".github/workflows/libexpat-version-check.yml"
TRIVYIGNORE = ".trivyignore"

DIGEST_RE = re.compile(r"sha256:([0-9a-f]{64})")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def env_pin(workflow: str, var: str) -> str:
    m = re.search(rf"^\s*{var}:\s*'([^']+)'\s*$", read(workflow), re.M)
    assert m, f"{workflow}: {var} not found"
    return m.group(1)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# --- 1. every base image is digest-pinned, and the pins agree with the scan env ----
python_pin = env_pin(SCAN_WORKFLOW, "PYTHON_BASE_IMAGE")
nginx_pin = env_pin(SCAN_WORKFLOW, "NGINX_FRONTEND_IMAGE")
postgres_pin = env_pin(SCAN_WORKFLOW, "POSTGRES_IMAGE")

for var, pin in (
    ("PYTHON_BASE_IMAGE", python_pin),
    ("NGINX_FRONTEND_IMAGE", nginx_pin),
    ("POSTGRES_IMAGE", postgres_pin),
):
    if not DIGEST_RE.search(pin):
        fail(f"{var} is not digest-pinned: {pin}")

for df in PYTHON_DOCKERFILES:
    pins = set(DIGEST_RE.findall(read(df)))
    if not pins:
        fail(f"{df} pins no python base image by digest")
    if pins != {DIGEST_RE.search(python_pin).group(1)}:
        fail(f"{df} pins {pins} but the scan env pins {DIGEST_RE.search(python_pin).group(1)}")

nginx_docker_pins = set(DIGEST_RE.findall(read(NGINX_DOCKERFILE)))
if nginx_docker_pins != {DIGEST_RE.search(nginx_pin).group(1)}:
    fail(
        f"{NGINX_DOCKERFILE} builds {nginx_docker_pins} but {SCAN_WORKFLOW} scans "
        f"{DIGEST_RE.search(nginx_pin).group(1)} — the gate is not covering the "
        f"image we ship"
    )

expat_pinned = env_pin(EXPAT_WORKFLOW, "PINNED_DIGEST")
if expat_pinned != "sha256:" + DIGEST_RE.search(nginx_pin).group(1):
    fail(f"{EXPAT_WORKFLOW} PINNED_DIGEST {expat_pinned} != {SCAN_WORKFLOW} {nginx_pin}")

# --- 2. the trivy action must be given a real input name -------------------------
# `scanner:` is not an input of aquasecurity/trivy-action; GitHub drops it with an
# "Unexpected input(s)" warning, so the scan silently runs with the default
# scanner set.
if re.search(r"^\s*scanner:", read(SCAN_WORKFLOW), re.M):
    fail(f"{SCAN_WORKFLOW} passes `scanner:` to trivy-action; the input is `scanners`")

# --- 3. every .trivyignore entry names a CVE and carries a justification ---------
for lineno, line in enumerate(read(TRIVYIGNORE).splitlines(), 1):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if not re.match(r"^(CVE-\d{4}-\d+|GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4})(\s|$)", stripped):
        fail(f"{TRIVYIGNORE}:{lineno} is not a CVE id: {stripped!r}")
    if "#" not in stripped:
        fail(f"{TRIVYIGNORE}:{lineno} has no justification comment: {stripped!r}")

def test_base_image_pins_are_consistent():
    """pytest entry point; the module-level asserts above do the real work."""


print("ok: base-image pins are consistent and every .trivyignore entry is justified")
