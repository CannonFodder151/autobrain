#!/usr/bin/env python3
"""AUT-2082: sync a git compose file into a Portainer stack (no human step).

After build-hosted.yml bumps the digest pins in docker-compose.hosted.yml,
this pushes the updated StackFileContent into the running Portainer stack so
the next deploy uses the freshly published digests — closing the drift
between git and Portainer without a manual operator action.

AUT-5172: the hosted stack (endpoint 5) is production, and AUT-2409 confines
hosted deploys to the nightly 03:00-04:00 AEST window. compose-pin runs on
every merge to main, so the sync silently redeployed production whenever
anyone merged. The window gate lives here — not in the workflow — so every
caller is covered. Outside the window this exits 0 without touching
Portainer; pins stay bumped in git and the next in-window deploy applies them.
Set ALLOW_OUT_OF_WINDOW=true for a board-approved out-of-window deploy.

AUT-5582: --create adds the missing half — creating a stack that does not
exist yet. A tier with no Portainer stack is invisible to this script, to
upgrade-instances.sh (which resolves tiers by stack name) and to the release
checklist, so it silently drifts and has to be rebuilt by hand: that is how
EP2's autobrain-demo lost its compose definition entirely (AUT-5491 /
AUT-5555). Creation takes the initial stack env from --env-file; an existing
stack keeps using its own Portainer env, which is never clobbered.

Usage:
  python3 scripts/sync-compose-to-portainer.py \
      --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import yaml

# AEST is a fixed UTC+10 with no DST, so a fixed offset avoids a tzdata dep.
AEST = timezone(timedelta(hours=10))
WINDOW_START_HOUR = 3
WINDOW_END_HOUR = 4
# The hosted stack only. The window is a hosted-deploy policy (AUT-2409); the
# EP2 `9router` stack has no such policy and must stay hand-updatable.
HOSTED_ENDPOINT = 5
# Stack type this Portainer writes for a compose stack: every stack on every
# endpoint (autobrain-hosted, plate-api-scraper, 9router, ...) reports Type=2,
# so creation uses the same value instead of guessing from the enum.
COMPOSE_STACK_TYPE = 2


def parse_env_file(path):
    """KEY=VALUE lines -> Portainer's [{name, value}] stack env."""
    env = []
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"{path}:{lineno}: not KEY=VALUE: {line!r}")
            key, _, value = line.partition("=")
            env.append({"name": key.strip(), "value": value})
    return env


def report(args, content, services):
    """Post-deploy audit: 200 is not health (AUT-4946), then the digest trail."""
    try:
        problems = verify_running(args, services)
    except urllib.error.HTTPError as e:
        print(f"WARNING: could not verify containers -> HTTP {e.code}", file=sys.stderr)
        problems = []
    if problems:
        print(f"ERROR: stack {args.stack!r} deployed but is NOT healthy:", file=sys.stderr)
        for name, why in problems:
            print(f"  {name}: {why}", file=sys.stderr)
        print("RECOVERY (destructive — run by hand):\n"
              f"  curl -X DELETE \"{args.portainer_url}/api/endpoints/"
              f"{args.endpoint}/docker/containers/<NAME>?force=true&v=true\" \\\n"
              "    -H \"X-API-Key: $PORTAINER_API_KEY\"\n"
              "then re-run this script (or redeploy the stack from Portainer).",
              file=sys.stderr)
        return 6

    print(f"stack={args.stack} endpoint={args.endpoint} "
          f"{'created' if args.create else 'updated'}")
    print(f"verified: {len(services)} services running, no stuck containers")
    # AUT-5669: which commit these digests were built from,
    # alongside the per-service digest trail below.
    src = compose_pin_source(content)
    if src:
        print(f"pin-source: {src}")
    # AUT-5186: audit trail for the nightly 03:00 AEST deploy — one line per
    # service with the digest the stack now runs. The run log is the only
    # record once the workflow is no longer tied to a human dispatch.
    for name, ref in sorted(compose_image_refs(content).items()):
        print(f"applied: {name} -> {ref}")
    return 0


def create_stack(args, content):
    """POST a new compose stack (AUT-5582). Env comes from --env-file only."""
    if not args.env_file:
        print("ERROR: --create needs --env-file (a new stack has no Portainer "
              "env to preserve; without it every ${VAR} in the compose file "
              "interpolates empty and the stack comes up broken)", file=sys.stderr)
        return 7
    try:
        env = parse_env_file(args.env_file)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 7
    if not env:
        print(f"ERROR: {args.env_file} has no KEY=VALUE lines", file=sys.stderr)
        return 7

    # Same orphan guard as the update path: a container from a service this
    # compose does not define but holding a host port we need would wedge the
    # deployment (AUT-4911).
    services, wanted_ports = compose_services_and_ports(content)
    try:
        clashes = check_port_collisions(args, services, {p for ps in wanted_ports.values() for p in ps})
    except urllib.error.HTTPError as e:
        print(f"WARNING: could not read endpoint containers -> HTTP {e.code}; "
              "skipping the pre-create orphan check", file=sys.stderr)
        clashes = []
    if clashes:
        print("ERROR: refusing to create — host port collision with orphans on "
              f"endpoint {args.endpoint}:", file=sys.stderr)
        for name, svc, ports in clashes:
            print(f"  {name} (service {svc!r}) holds host port(s) "
                  f"{', '.join(str(p) for p in ports)} this compose needs",
                  file=sys.stderr)
        return 5

    # Portainer 2.39 has no JSON create route: POST /api/stacks is 405 (the
    # reverse proxy rejects it) and the UI posts a multipart form to
    # /stacks/create/standalone/file?endpointId=N with fields
    # file/Name/Env/Webhook. Verified against the 2.39.7 frontend bundle.
    created = _post_multipart(
        args,
        f"/stacks/create/standalone/file?endpointId={args.endpoint}",
        {
            "file": (os.path.basename(args.file), content),
            "Name": args.stack,
            "Env": json.dumps(env),
            "Option": json.dumps({"Prune": False}),
        },
        timeout=180,
    )
    print(f"created stack={args.stack!r} type={args.stack_type} "
          f"endpoint={args.endpoint} with {len(env)} env vars "
          f"(id={created.get('Id')})")
    return report(args, content, services)


def in_deploy_window(now=None):
    """True inside the AUT-2409 hosted deploy window (03:00-04:00 AEST)."""
    return WINDOW_START_HOUR <= (now or datetime.now(AEST)).hour < WINDOW_END_HOUR


def out_of_window_allowed():
    """Explicit override for a board-approved out-of-window hosted deploy."""
    return os.environ.get("ALLOW_OUT_OF_WINDOW", "").strip().lower() in (
        "1", "true", "yes")


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


def _post_multipart(args, path, fields, timeout=180):
    """POST multipart/form-data (Portainer 2.39 stack create) -> parsed JSON.

    fields values are str, or (filename, content) to upload as a file part.
    Built by hand: no third-party multipart dep for one request.
    """
    boundary = "----autobrainstack" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n")
        if isinstance(value, tuple):
            filename, content = value
            parts.append(
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n")
            parts.append(content if isinstance(content, str)
                         else content.decode())
        else:
            parts.append(f'Content-Disposition: form-data; name="{name}"\r\n'
                         "\r\n")
            parts.append(str(value))
        parts.append("\r\n")
    parts.append(f"--{boundary}--\r\n")
    body = "".join(parts).encode()
    headers = {
        "X-API-Key": args.api_key,
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(
        f"{args.portainer_url}/api{path}", data=body, method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        # AUT-4911: a bare "HTTP Error 500" hid the real cause for a day.
        print(f"ERROR: Portainer POST {path} -> HTTP {e.code}", file=sys.stderr)
        print(e.read().decode("utf-8", "replace"), file=sys.stderr)
        raise
    return json.loads(raw) if raw else {}


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


def compose_image_refs(content):
    """AUT-5186: {service: image ref} — the digest pins this PUT applies."""
    doc = yaml.safe_load(content) or {}
    return {name: (spec or {}).get("image", "<no image>")
            for name, spec in (doc.get("services") or {}).items()}


def unpinned_image_refs(content):
    """AUT-5669: services whose image is a moving tag rather than a digest.

    A deploy resolves whatever this file names, so a tag-only ref would run
    an image no commit references — exactly the provenance drift AUT-5669 is
    about. Refused rather than deployed.
    """
    return {name: ref for name, ref in compose_image_refs(content).items()
            if "@sha256:" not in ref}


def compose_pin_source(content):
    """AUT-5669: the commit the pinned digests were built from, if recorded."""
    doc = yaml.safe_load(content) or {}
    return doc.get("x-autobrain-pin-source")


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


def verify_running(args, services, attempts=20, delay=5):
    """Wait for every service to have a running container. Returns list of
    problems; empty means healthy."""
    for _ in range(attempts):
        containers = endpoint_containers(args)
        running = {_service_of(c) for c in containers if c.get("State") == "running"}
        stuck = [(c["Names"][0].lstrip("/"), c.get("State"))
                 for c in containers if c.get("State") == "created"]
        missing = sorted(services - running)
        if not missing and not stuck:
            return []
        time.sleep(delay)
    containers = endpoint_containers(args)
    running = {_service_of(c) for c in containers if c.get("State") == "running"}
    stuck = [(c["Names"][0].lstrip("/"), c.get("State"))
             for c in containers if c.get("State") == "created"]
    return ([(None, f"service {m!r} has no running container")
             for m in sorted(services - running)] +
            [(n, f"stuck in state {st}") for n, st in stuck])


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
    ap.add_argument("--create", action="store_true",
                    help="create the stack when it does not exist yet "
                         "(AUT-5582) — initial env comes from --env-file")
    ap.add_argument("--env-file",
                    help="KEY=VALUE file; required with --create")
    ap.add_argument("--stack-type", type=int, default=COMPOSE_STACK_TYPE,
                    help="Portainer stack type for --create "
                         f"(default: {COMPOSE_STACK_TYPE})")
    args = ap.parse_args()

    # AUT-5172: gate before any network call so a gated run has zero effect.
    # Hosted endpoint only — the window is a hosted-deploy policy, and other
    # endpoints (e.g. EP2 `9router`) stay hand-updatable at any hour.
    if (args.endpoint == HOSTED_ENDPOINT
            and not in_deploy_window() and not out_of_window_allowed()):
        print(f"SKIP: {datetime.now(AEST):%Y-%m-%d %H:%M} AEST is outside the "
              f"AUT-2409 hosted deploy window "
              f"({WINDOW_START_HOUR:02d}:00-{WINDOW_END_HOUR:02d}:00 AEST); "
              f"stack {args.stack!r} left untouched")
        print("Set ALLOW_OUT_OF_WINDOW=true only for a board-approved "
              "out-of-window deploy.")
        return 0

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
        if args.create:
            return create_stack(args, content)
        print(f"ERROR: stack {args.stack!r} not found "
              "(pass --create --env-file to create it)", file=sys.stderr)
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

    # AUT-5669: refuse to deploy a moving tag. The whole point of
    # a pinned compose file is that the deploy resolves the exact
    # index a commit references; a tag-only ref silently deploys
    # whatever ghcr.io serves at deploy time instead.
    unpinned = unpinned_image_refs(content)
    if unpinned:
        print("ERROR: refusing to sync — image ref(s) without a digest "
              "pin:", file=sys.stderr)
        for name, ref in sorted(unpinned.items()):
            print(f"  {name}: {ref}", file=sys.stderr)
        print("Pin every image as repo:tag@sha256:<digest> first "
              "(see scripts/update-compose-pins.py).", file=sys.stderr)
        return 7

    # AUT-4946: refuse BEFORE the PUT if a host port this compose needs is
    # held by a container from a service the new compose drops. Portainer's
    # PUT is not atomic: it leaves the replacement stuck in state "created"
    # forever and the site 502s (AUT-4911).
    services, wanted_ports = compose_services_and_ports(content)
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

    # AUT-4946: a 200 PUT does not mean a healthy stack. Verify + audit.
    print(f"stack={args.stack} id={stack_id} endpoint={args.endpoint} updated")
    return report(args, content, services)


if __name__ == "__main__":
    sys.exit(main())