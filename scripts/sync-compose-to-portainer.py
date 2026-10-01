#!/usr/bin/env python3
"""AUT-2082: sync a git compose file into a Portainer stack (no human step).

After build-hosted.yml bumps the digest pins in docker-compose.hosted.yml,
this pushes the updated StackFileContent into the running Portainer stack so
the next deploy uses the freshly published digests — closing the drift
between git and Portainer without a manual operator action.

Usage:
  python3 scripts/sync-compose-to-portainer.py \
      --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True)
    ap.add_argument("--endpoint", required=True, type=int)
    ap.add_argument("--file", required=True)
    ap.add_argument("--portainer-url", default=os.environ.get(
        "PORTAINER_URL", "https://portainer.nathanmartina.com"))
    ap.add_argument("--api-key", default=os.environ.get("PORTAINER_API_KEY"))
    ap.add_argument("--pull-image", action="store_true", default=True,
                    help="force a pull so the new digest is fetched (default: true)")
    args = ap.parse_args()

    if not args.api_key:
        print("ERROR: PORTAINER_API_KEY not set", file=sys.stderr)
        return 2

    with open(args.file) as f:
        content = f.read()

    # Resolve stack id by name (Portainer 2.45 ignores ?name=).
    api = f"{args.portainer_url}/api"
    req = urllib.request.Request(
        f"{api}/stacks",
        headers={"X-API-Key": args.api_key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        stacks = json.load(r)
    ids = [s for s in stacks if s.get("Name") == args.stack]
    if not ids:
        print(f"ERROR: stack {args.stack!r} not found", file=sys.stderr)
        return 1
    stack_id = ids[0]["Id"]

    # Fetch current env to preserve existing stack env (never clobber).
    # AUT-4778: env lives on GET /api/stacks/{id}; GET /api/stacks/{id}/file
    # returns only StackFileContent, so reading Env from /file sent Env: []
    # and wiped all 49 stack env vars on every sync. Portainer then failed
    # compose interpolation of ${POSTGRES_USER:?...} and returned HTTP 500.
    req = urllib.request.Request(
        f"{api}/stacks/{stack_id}",
        headers={"X-API-Key": args.api_key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        current = json.load(r)
    env = current.get("Env") or []
    if not env:
        print("ERROR: stack env is empty — refusing to sync (would wipe it)",
              file=sys.stderr)
        return 3

    body = {
        "StackFileContent": content,
        "Env": env,
        "Prune": False,
    }
    params = f"?endpointId={args.endpoint}"
    if args.pull_image:
        params += "&pullImage=true"

    req = urllib.request.Request(
        f"{api}/stacks/{stack_id}{params}",
        data=json.dumps(body).encode(),
        method="PUT",
        headers={
            "X-API-Key": args.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    # AUT-4911: print the Portainer response body on failure. The bare
    # "HTTP Error 500" hid the actual cause ("compose build operation failed:
    # listing workers for Build") for a whole day of red CI.
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"ERROR: Portainer PUT /stacks/{stack_id} -> HTTP {e.code}", file=sys.stderr)
        print(body, file=sys.stderr)
        return 4
    print(f"stack={args.stack} id={stack_id} endpoint={args.endpoint} updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())