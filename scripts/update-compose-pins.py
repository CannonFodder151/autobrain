#!/usr/bin/env python3
"""AUT-2082: rewrite image digest pins in the AutoBrain compose files.

After build-hosted.yml publishes multi-arch manifests, this updates the
`@sha256:...` pins in docker-compose.hosted.yml so the git checkout always
matches the freshly published digests. Exits 0 if anything changed, 1 if no
change needed, 3 if this run is stale and the pin must not move.

AUT-5669: the pin also records WHICH commit produced it, in the
`x-autobrain-pin-source` top-level key. A run whose commit is an ancestor of
the recorded one is stale (queued behind a newer push, or an old run re-run
after a newer one already pinned) and must never move the pin backwards.
The recorded sha also makes "which commit built the running image"
answerable straight from git.

Usage: python3 scripts/update-compose-pins.py \
        backend=sha256:... ai=sha256:... frontend=sha256:... \
        [--file docker-compose.hosted.yml] [--source-sha <commit>]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

# service -> repo prefix as pinned in docker-compose.hosted.yml
PIN_MAP = {
    "backend":  "ghcr.io/cannonfodder151/autobrain-backend",
    "ai":       "ghcr.io/cannonfodder151/autobrain-ai",
    "frontend": "ghcr.io/cannonfodder151/autobrain-frontend",
}

# AUT-5669: compose extension key recording the commit whose build produced
# the pinned digests.
PROVENANCE_KEY = "x-autobrain-pin-source"
_PROV_RE = re.compile(rf'^{PROVENANCE_KEY}:\s*"?([0-9a-f]{{40}})"?\s*$', re.M)
_PROV_LINE_RE = re.compile(rf"^{PROVENANCE_KEY}:.*$", re.M)


def pin_source(text):
    """The commit recorded as the source of the current pins, or None."""
    m = _PROV_RE.search(text)
    return m.group(1) if m else None


def _is_ancestor(older, newer):
    """git merge-base --is-ancestor older newer.

    Returns True/False. An unusable git invocation (missing object, not a
    repo) returns None so the caller can fail open rather than wedge every
    pin bump on a bad ref.
    """
    rc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode
    if rc == 0:
        return True
    if rc == 1:
        return False
    return None


def is_stale(text, source_sha):
    """True when a newer commit already owns the pin."""
    if not source_sha:
        return False
    recorded = pin_source(text)
    if not recorded or recorded == source_sha:
        return False
    older_than_pin = _is_ancestor(source_sha, recorded)
    if older_than_pin is None:
        print(f"WARNING: could not compare {source_sha[:8]} against recorded "
              f"{recorded[:8]}; proceeding", file=sys.stderr)
        return False
    return older_than_pin


def set_provenance(text, source_sha):
    """Stamp (or refresh) the pin-source key, just above the compose body."""
    line = f'{PROVENANCE_KEY}: "{source_sha}"'
    if _PROV_LINE_RE.search(text):
        return _PROV_LINE_RE.sub(line, text, count=1)
    lines = text.splitlines(keepends=True)
    for i, raw in enumerate(lines):
        if raw.strip() and not raw.lstrip().startswith("#"):
            break
    else:
        i = len(lines)
    return "".join(lines[:i] + [
        f"# AUT-5669: commit whose build produced the digests pinned below.\n",
        f"{line}\n", "\n",
    ] + lines[i:])


def parse_args():
    ap = argparse.ArgumentParser(
        description="Bump compose image digest pins to published multi-arch digests")
    ap.add_argument("--file", default="docker-compose.hosted.yml",
                    help="compose file to rewrite (default: docker-compose.hosted.yml)")
    ap.add_argument("--source-sha", default=None,
                    help="commit whose build produced the pins (AUT-5669)")
    ap.add_argument("pairs", nargs="*",
                    help="svc=sha256:hexdigest, e.g. backend=sha256:abc123..")
    return ap.parse_args()


def main():
    args = parse_args()
    if args.source_sha and not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        print(f"ERROR: --source-sha must be a 40-hex commit sha, "
              f"got {args.source_sha!r}", file=sys.stderr)
        return 2
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

    if is_stale(text, args.source_sha):
        print(f"stale run: pin is owned by a newer commit ({pin_source(text)[:8]}) "
              f"— refusing to move {p} backwards (AUT-5669)")
        return 3

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

    # Only re-stamp provenance when a digest actually moved, so a rebuild
    # that reproduced the same index does not commit noise to main.
    if text != orig:
        text = set_provenance(text, args.source_sha)

    if text == orig:
        print("no changes")
        return 1
    p.write_text(text)
    print(f"updated {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
