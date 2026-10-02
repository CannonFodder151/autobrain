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
import re
import sys
import time
import urllib.error
import urllib.request

import yaml


def _api(args, path, method="GET", body=None, timeout=30):
    """Call the Portainer API and return parsed JSON."""
    headers = {"X-API-Key": args.api_key, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{args.portainer_url}/api{path}", data=data, method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def compose_services_and_ports(content):
    """Return (service names, {service: set(host ports)}).

    Handles both short syntax ("127.0.0.1:8080:8080") and long syntax
    ({published: ...}) port entries.
    """
    doc = yaml.safe_load(content) or {}
    services = doc.get("services") or {}
    ports = {}
    for name, spec in services.items():
        found = set()
        for entry in (spec or {}).get("ports") or []:
            if isinstance(entry, dict):
                published = entry.get("published")
                if published:
                    found.add(int(published))
                continue
            parts = str(entry).split("/")[0].split(":")
            if len(parts) >= 2:  # host:container
                try:
                    found.add(int(parts[-2]))
                except ValueError:
                    pass
            else:  # container-only — published on an ephemeral host port
                try:
                    found.add(int(parts[0]))
                except ValueError:
                    pass
        if found:
            ports[name] = found
    return set(services), ports


def compose_image_digests(content):
    """Return {service: 'sha256:...'} for every digest-pinned service image."""
    doc = yaml.safe_load(content) or {}
    digests = {}
    for name, spec in (doc.get("services") or {}).items():
        m = re.search(r"@sha256:([0-9a-f]{64})", (spec or {}).get("image") or "")
        if m:
            digests[name] = "sha256:" + m.group(1)
    return digests


def endpoint_containers(args):
    """All containers on the endpoint (including stopped/unused ones)."""
    return _api(args, f"/endpoints/{args.endpoint}/docker/containers/json?all=true")


def _service_of(c):
    return (c.get("Labels") or {}).get("com.docker.compose.service") or ""


def _published_ports(c):
    return {p["PublicPort"] for p in c.get("Ports") or []
            if p.get("PublicPort")}


def check_port_collisions(args, services, wanted_ports):
    """Refuse if a host port the new compose wants is held by a container whose
    service is NOT in the new compose (an orphan Portainer will not reap)."""
    containers = endpoint_containers(args)
    problems = []
    for c in containers:
        svc = _service_of(c)
        if svc in services:
            continue
        clash = _published_ports(c) & set(wanted_ports)
        if clash:
            problems.append((c["Names"][0].lstrip("/"), svc or "<no label>",
                             sorted(clash)))
    return problems


def verify_running(args, services, digests=None, attempts=20, delay=5):
    """Wait for every service to have a running container. Returns list of
    problems; empty means healthy.

    digests (AUT-5132): {service: 'sha256:...'} from the compose. A digest
    pin plus a running container whose ImageID differs means the redeploy did
    not move the image — the exact silent no-op that let PR #870 sit merged in
    main but un-deployed for a whole day. Compare ImageID (config digest), not
    Image: for the single-platform images Portainer runs, ImageID equals the
    compose's manifest pin for every service in the hosted stack.

    ponytail: checks image identity only. Command/env drift is covered by the
    digest changing plus post-deploy-smoke.sh; add a per-container
    /containers/{id}/json command compare if a compose-only edit ever needs a
    second alarm.
    """
    digests = digests or {}
    containers = endpoint_containers(args)
    def _problems():
        running = {_service_of(c): c for c in containers if c.get("State") == "running"}
        stuck = [(c["Names"][0].lstrip("/"), c.get("State"))
                 for c in containers if c.get("State") == "created"]
        out = ([(None, f"service {m!r} has no running container")
                for m in sorted(set(services) - set(running))] +
               [(n, f"stuck in state {st}") for n, st in stuck])
        for svc, want in sorted(digests.items()):
            c = running.get(svc)
            if c is None:
                continue  # already reported as missing/stuck
            got = c.get("ImageID") or ""
            if got != want:
                out.append((svc, f"image did not move — compose pins "
                                 f"{want[7:19]} but running container is "
                                 f"{(got or '<none>')[7:19] or '<none>'}"))
        return out
    for _ in range(attempts):
        containers = endpoint_containers(args)
        problems = _problems()
        if not problems:
            return []
        time.sleep(delay)
    containers = endpoint_containers(args)
    return _problems()


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

    # AUT-4946: refuse BEFORE the PUT if a host port this compose needs is
    # held by a container from a service the new compose drops. Portainer's
    # PUT is not atomic: it leaves the replacement stuck in state "created"
    # forever and the site 502s (AUT-4911).
    services, wanted_ports = compose_services_and_ports(content)
    digests = compose_image_digests(content)
    flat_wanted = {p for ps in wanted_ports.values() for p in ps}
    try:
        clashes = check_port_collisions(args, services, flat_wanted)
    except urllib.error.HTTPError as e:
        print(f"WARNING: could not read endpoint containers -> HTTP {e.code}; "
              "skipping the pre-PUT orphan check", file=sys.stderr)
        clashes = []
    if clashes:
        print(f"ERROR: refusing to sync — host port collision with orphans on "
              f"endpoint {args.endpoint}:", file=sys.stderr)
        for name, svc, ports in clashes:
            print(f"  {name} (service {svc!r}) holds host port(s) "
                  f"{', '.join(str(p) for p in ports)} that the new compose "
                  f"needs, but {svc!r} is not a service in the incoming compose",
                  file=sys.stderr)
        print("RECOVERY (destructive — run by hand, then re-run this sync):\n"
              f"  curl -X DELETE \"{args.portainer_url}/api/endpoints/"
              f"{args.endpoint}/docker/containers/<NAME>?force=true&v=true\" \\\n"
              f"    -H \"X-API-Key: $PORTAINER_API_KEY\"", file=sys.stderr)
        return 5

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

    # AUT-4946: a 200 PUT does not mean a healthy stack. Verify.
    try:
        problems = verify_running(args, services, digests)
    except urllib.error.HTTPError as e:
        print(f"WARNING: could not verify containers -> HTTP {e.code}", file=sys.stderr)
        problems = []
    if problems:
        print(f"ERROR: stack {args.stack!r} updated but is NOT healthy:", file=sys.stderr)
        for name, why in problems:
            print(f"  {name}: {why}", file=sys.stderr)
        print("RECOVERY (destructive — run by hand):\n"
              f"  curl -X DELETE \"{args.portainer_url}/api/endpoints/"
              f"{args.endpoint}/docker/containers/<NAME>?force=true&v=true\" \\\n"
              "    -H \"X-API-Key: $PORTAINER_API_KEY\"\n"
              "then re-run this script (or redeploy the stack from Portainer).",
              file=sys.stderr)
        return 6

    print(f"stack={args.stack} id={stack_id} endpoint={args.endpoint} updated")
    print(f"verified: {len(services)} services running, no stuck containers")
    return 0


if __name__ == "__main__":
    sys.exit(main())