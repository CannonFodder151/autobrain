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

    # preserve env — GET /stacks/{id}/file returns Env: null on some endpoints,
    # so we must read the real env from GET /stacks/{id} (the stack object).
    req = urllib.request.Request(f"{api}/stacks/{stack_id}", headers={"X-API-Key": args.api_key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        stack_obj = json.load(r)
    env = stack_obj.get("Env") or []

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
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = r.read().decode()
    print(f"stack={args.stack} id={stack_id} endpoint={args.endpoint} -> {resp[:200]}")
    # verify the persisted stack file matches what we pushed (Status=1 means OK)
    req = urllib.request.Request(f"{api}/stacks/{stack_id}/file", headers={"X-API-Key": args.api_key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        verify = json.load(r)
    verify_status = verify.get("Status")
    verify_content = verify.get("StackFileContent", "")
    if verify_status != 1:
        print(f"WARNING: post-PUT file status={verify_status}, expected 1", file=sys.stderr)
    if verify_content.strip() != content.strip():
        print("WARNING: post-PUT file content does not match what was pushed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())