#!/usr/bin/env python3
"""AUT-2175: rewrite image digest pins in the AutoBrain k8s manifests.

After build-hosted.yml publishes multi-arch manifests, this updates the
image references in infra/k8s/*.yaml from `repo:tag` to `repo@sha256:...`
so k8s never pulls a different image for the same commit.

Usage: python3 scripts/update-k8s-pins.py \
        backend=sha256:... ai=sha256:... frontend=sha256:... \
        [--dir infra/k8s]
"""
import argparse
import re
import sys
from pathlib import Path

PIN_MAP = {
    "backend":  "ghcr.io/cannonfodder151/autobrain-backend",
    "ai":       "ghcr.io/cannonfodder151/autobrain-ai",
    "frontend": "ghcr.io/cannonfodder151/autobrain-frontend",
}

# files that need a given service's digest applied
SERVICE_FILES = {
    "backend":  ["backend.yaml"],
    "ai":       ["ai.yaml"],
    "frontend": ["frontend.yaml"],
}


def parse_args():
    ap = argparse.ArgumentParser(
        description="Bump k8s manifest image pins to published multi-arch digests")
    ap.add_argument("--dir", default="infra/k8s",
                    help="directory containing k8s manifests (default: infra/k8s)")
    ap.add_argument("pairs", nargs="*",
                    help="svc=sha256:hexdigest, e.g. backend=sha256:abc123..")
    return ap.parse_args()


def main():
    args = parse_args()
    pins = {}
    for a in args.pairs:
        if "=" not in a:
            print(f"ERROR: expected svc=digest, got {a!r}", file=sys.stderr)
            return 2
        k, v = a.split("=", 1)
        if not v.startswith("sha256:"):
            print(f"ERROR: digest for {k} must be sha256:..., got {v!r}", file=sys.stderr)
            return 2
        pins[k] = v

    k8s_dir = Path(args.dir)
    any_changed = False

    for svc, digest in pins.items():
        repo_prefix = PIN_MAP.get(svc)
        if not repo_prefix:
            print(f"ERROR: unknown service {svc!r}", file=sys.stderr)
            return 2
        for fname in SERVICE_FILES.get(svc, []):
            p = k8s_dir / fname
            if not p.exists():
                print(f"WARN: {p} not found — skipping {svc}", file=sys.stderr)
                continue
            text = p.read_text()
            orig = text
            # Match `repo:tag` without an existing @sha256: pin
            pattern = re.compile(
                r"(" + re.escape(repo_prefix) + r"):([a-z0-9_.-]+)"
                r"(?!@sha256:)"
            )
            new_ref = f"\\1@{digest}"
            text, n = pattern.subn(new_ref, text)
            if n == 0:
                print(f"WARN: no match for {svc} in {p}", file=sys.stderr)
            elif text != orig:
                p.write_text(text)
                any_changed = True
                print(f"updated {p}")

    if not any_changed:
        print("no changes")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
