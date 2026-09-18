#!/usr/bin/env python3
"""AUT-2175/D4: rewrite image digest pins in the AutoBrain k8s manifests.

After build-hosted.yml publishes multi-arch manifests, this updates the
`@sha256:...` pins in infra/k8s/*.yaml so the helm/k8s deploy refs always
match the freshly published digests. Exits 0 if anything changed, 1 if no
change needed.

Usage: python3 scripts/update-k8s-pins.py \
        backend=sha256:... worker=sha256:... ai=sha256:... frontend=sha256:...

Image refs in the manifests use the short form `autobrain-<svc>:latest` with
`imagePullPolicy: Always`. This script rewrites each to the full GHCR ref with
a digest, e.g. `ghcr.io/cannonfodder151/autobrain-backend:hosted-amd64@sha256:...`
and flips `imagePullPolicy: Always` to `IfNotPresent` (digests are immutable,
so Always provides no benefit and triggers redundant registry round-trips).
"""

import argparse
import re
import sys
from pathlib import Path

K8S_DIR = Path(__file__).resolve().parent.parent / "infra" / "k8s"

# service -> full ghcr.io repo path
PIN_MAP = {
    "backend":  "ghcr.io/cannonfodder151/autobrain-backend",
    "worker":   "ghcr.io/cannonfodder151/autobrain-backend",
    "ai":       "ghcr.io/cannonfodder151/autobrain-ai",
    "frontend": "ghcr.io/cannonfodder151/autobrain-frontend",
}

# tag to use on the pinned ref (arbitrary label that travels with the digest;
# harmless cosmetic since k8s resolves purely on the digest). Using :hosted
# keeps it readable in `kubectl get` / `k9s` output.
PIN_TAG = "hosted"


def parse_args():
    ap = argparse.ArgumentParser(
        description="Bump k8s image digest pins to published multi-arch digests")
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

    changed_any = False

    for svc, digest in pins.items():
        repo_prefix = PIN_MAP.get(svc)
        if not repo_prefix:
            print(f"ERROR: unknown service {svc!r}", file=sys.stderr)
            return 2

        short_name = f"autobrain-{svc}"

        for manifest in sorted(K8S_DIR.glob("*.yaml")):
            text = manifest.read_text()
            orig = text

            # Match `autobrain-<svc>:latest` (with or without a pull policy line).
            # The k8s manifests use the short form: `image: autobrain-<svc>:latest`.
            # Multiple manifests reference the same backend image (worker.yaml
            # references autobrain-backend for both worker + beat containers).
            pattern = re.compile(
                r"image:\s+" + re.escape(short_name) + r":[a-zA-Z0-9_.-]+")
            new_ref = f"image: {repo_prefix}:{PIN_TAG}@{digest}"
            text, n = pattern.subn(new_ref, text)
            if n:
                changed_any = True
                print(f"  {manifest.name}: pinned {short_name} -> {digest[:19]}… ({n} ref(s))")

            # Flip imagePullPolicy: Always -> IfNotPresent once pinned by digest.
            # Digests are immutable, so Always just adds a redundant registry
            # HEAD call on every pod start with no correctness benefit.
            if n:
                text, pn = re.subn(
                    r"(image: " + re.escape(repo_prefix) + r":" + re.escape(PIN_TAG) + r"@" + re.escape(digest) + r"\n)(\s+imagePullPolicy: )Always",
                    r"\g<1>\g<2>IfNotPresent",
                    text,
                )
                if pn:
                    changed_any = True

            if text != orig:
                manifest.write_text(text)

    if not changed_any:
        print("no changes")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
