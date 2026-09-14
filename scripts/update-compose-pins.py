#!/usr/bin/env python3
"""AUT-2082: rewrite image digest pins in the AutoBrain compose files.

After build-hosted.yml publishes multi-arch manifests, this updates the
`@sha256:...` pins in docker-compose.hosted.yml so the git checkout always
matches the freshly published digests. Exits 0 if anything changed, 1 if no
change needed.

Usage: python3 scripts/update-compose-pins.py \
        backend=sha256:... worker=sha256:... ai=sha256:... frontend=sha256:... \
        [--file docker-compose.hosted.yml]
"""
import argparse
import re
import sys
from pathlib import Path

# service -> repo prefix as pinned in docker-compose.hosted.yml
PIN_MAP = {
    "backend":  "ghcr.io/cannonfodder151/autobrain-backend",
    "worker":   "ghcr.io/cannonfodder151/autobrain-worker",
    "ai":       "ghcr.io/cannonfodder151/autobrain-ai",
    "frontend": "ghcr.io/cannonfodder151/autobrain-frontend",
}


def parse_args():
    ap = argparse.ArgumentParser(
        description="Bump compose image digest pins to published multi-arch digests")
    ap.add_argument("--file", default="docker-compose.hosted.yml",
                    help="compose file to rewrite (default: docker-compose.hosted.yml)")
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

    p = Path(args.file)
    text = p.read_text()
    orig = text

    for svc, digest in pins.items():
        repo_prefix = PIN_MAP.get(svc)
        if not repo_prefix:
            print(f"ERROR: unknown service {svc!r}", file=sys.stderr)
            return 2
        # Match `repo:tag@sha256:...` or `repo@sha256:...` (frontend has no tag).
        pattern = re.compile(
            r"(" + re.escape(repo_prefix) + r"(?::[a-z0-9_.-]+)?)"
            r"@sha256:[a-f0-9]{64}"
        )
        new_ref = f"{repo_prefix}:hosted@{digest}"
        text, n = pattern.subn(new_ref, text)
        if n == 0:
            print(f"WARN: no pin matched for {svc} ({new_ref})", file=sys.stderr)

    if text == orig:
        print("no changes")
        return 1
    p.write_text(text)
    print(f"updated {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
