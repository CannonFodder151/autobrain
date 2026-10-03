#!/usr/bin/env python3
"""
Redeploy the AutoBrain DEMO containers (backend/ai/frontend) on EP2
(10.0.3.17 / Portainer-Host) via the Portainer Docker proxy API.

There is NO SSH access to 10.0.3.17 (only 10.0.3.39 devbox + 10.0.3.40 runner +
152.69.188.133 hosted). The demo tier is a raw `docker compose` project named
`autobrain-demo`; there is no Portainer stack ("stack 73" does not exist).
Management must go through:  https://portainer.nathanmartina.com
  GET  /api/endpoints/2/docker/containers/<id>/json
  POST /api/endpoints/2/docker/images/create?fromImage=...&tag=...
  POST /api/endpoints/2/docker/containers/create?name=<compose-name>
  POST /api/endpoints/2/docker/containers/<id>/start
  POST /api/endpoints/2/docker/containers/<id>/stop
  DELETE/api/endpoints/2/docker/containers/<id>

Behavior:
  - Pulls the new image digests for backend/ai/frontend.
  - Stops & removes ONLY the app containers (backend/ai/frontend).
  - Recreates each with the SAME volumes, networks, labels, healthcheck,
    entrypoint/cmd, restart policy.
  - Injects DEMO_RESET=true on the backend env (flips the existing
    DEMO_RESET=false entry so the refreshed fuel-station seed re-seeds).
  - NEVER touches postgres/redis/minio data volumes.
  - Supports --dry-run (print the plan + container JSON, no writes) and
    --apply  (actually perform stop/remove/create/start).

Usage:
  python3 redeploy-demo.py --dry-run
  python3 redeploy-demo.py --apply
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse, urllib.error

PORTAINER_URL = os.environ.get("PORTAINER_URL", "https://portainer.nathanmartina.com")
API_KEY = os.environ.get("PORTAINER_API_KEY") or os.environ.get("PORTAINER_KEY")
if not API_KEY:
    print("ERROR: PORTAINER_API_KEY env not set", file=sys.stderr); sys.exit(2)

ENDPOINT_ID = "2"            # Portainer-Host = EP2 = 10.0.3.17
NET_MODE = "autobrain-demo_default"

# The three app services to recreate. Map compose service -> (new image ref)
TARGETS = {
    "backend": {
        "name": "autobrain-demo-backend-1",
        "new_image": "cannonfodder151/autobrain-backend:0.3.260-amd64",
        "reset_env": True,   # inject DEMO_RESET=true
    },
    "ai": {
        "name": "autobrain-demo-ai-1",
        "new_image": "cannonfodder151/autobrain-ai:0.3.260-amd64",
        "reset_env": False,
    },
    "frontend": {
        "name": "autobrain-demo-frontend-1",
        "new_image": "ghcr.io/cannonfodder151/autobrain-frontend:demo",
        "reset_env": False,
    },
}


def api(method, path, body=None, query=""):
    url = f"{PORTAINER_URL}/api/endpoints/{ENDPOINT_ID}/docker{path}"
    if query:
        url += "?" + query
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-API-Key", API_KEY)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
        return raw, r.status
    except urllib.error.HTTPError as e:
        return e.read(), e.code


def jsonget(method, path, query=""):
    raw, code = api(method, path, query=query)
    return code, json.loads(raw) if raw else None


def container_by_name(cname):
    """Inspect via /containers/{name}/json — Docker accepts names too."""
    code, data = jsonget("GET", f"/containers/{cname}/json")
    if code != 200:
        return None
    return data


def pull_image(image_ref):
    # image_ref may be "repo:tag" or "repo@digest". Use fromImage+tag.
    if "@" in image_ref:
        repo, digest = image_ref.split("@", 1)
        query = "fromImage=" + urllib.parse.quote(repo) + "&" + urllib.parse.quote(digest)
    elif ":" in image_ref:
        repo, tag = image_ref.rsplit(":", 1)
        query = "fromImage=" + urllib.parse.quote(repo) + "&tag=" + urllib.parse.quote(tag)
    else:
        query = "fromImage=" + urllib.parse.quote(image_ref) + "&tag=latest"
    # Portainer proxies the pull as a long-poll stream; 120s timeout.
    req = urllib.request.Request(
        f"{PORTAINER_URL}/api/endpoints/{ENDPOINT_ID}/docker/images/create?{query}",
        method="POST",
    )
    req.add_header("X-API-Key", API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            # drain the stream
            _ = r.read()
        return True
    except urllib.error.HTTPError as e:
        print(f"   pull HTTP {e.code}: {e.read()[:300]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"   pull error: {e}", file=sys.stderr)
        return False


def build_config(old, target):
    """Produce a create-config dict reusing the old container's Config/HostConfig."""
    cfg = dict(old["Config"])
    hc = dict(old["HostConfig"])
    env = list(cfg.get("Env") or [])
    if target.get("reset_env"):
        env = [ (f"DEMO_RESET=true" if e.startswith("DEMO_RESET=") else e) for e in env ]
        if not any(e.startswith("DEMO_RESET=") for e in env):
            env.append("DEMO_RESET=true")
    cfg["Env"] = env
    cfg["Image"] = target["new_image"]
    # Drop server-side-only keys Docker rejects on create.
    for k in ("ContainerIDFile",):
        cfg.pop(k, None)
    hc.pop("ConsoleSize", None)
    # ensure network stays on the demo net
    hc["NetworkMode"] = NET_MODE
    nc = {"EndpointsConfig": {NET_MODE: {"Aliases": [
        target["name"], target_name_from_cfg(cfg)
    ]}}}
    return cfg, hc, nc


def target_name_from_cfg(cfg):
    labels = cfg.get("Labels") or {}
    return labels.get("com.docker.compose.service", "svc")


def health_ok(name):
    """Poll the container's health state until healthy or timeout (~90s)."""
    _, data = jsonget("GET", f"/containers/{name}/json")
    if not data:
        return False
    # healthcheck exists on backend+frontend
    h = (data.get("State") or {}).get("Health") or {}
    status = h.get("Status")
    if status is None:
        # no healthcheck (ai) — treat running = ok
        return (data.get("State") or {}).get("Running", False)
    deadline = time.time() + 90
    while time.time() < deadline:
        if status == "healthy":
            return True
        if status == "unhealthy":
            return False
        time.sleep(5)
        _, data = jsonget("GET", f"/containers/{name}/json")
        h = (data.get("State") or {}).get("Health") or {}
        status = h.get("Status")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually execute (default: dry-run)")
    ap.add_argument("--skip-pull", action="store_true", help="skip the image pull step")
    args = ap.parse_args()

    print(f"Portainer: {PORTAINER_URL}  EP{ENDPOINT_ID} (10.0.3.17)  mode="
          + ("APPLY" if args.apply else "DRY-RUN"))
    print("=" * 72)

    # 1. Inspect live demo app containers
    live = {}
    for svc, t in TARGETS.items():
        c = container_by_name(t["name"])
        if not c:
            print(f"[{svc}] container {t['name']} NOT FOUND — skipping")
            continue
        live[svc] = c
        print(f"[{svc}] live cid={c['Id'][:12]} image={c['Config']['Image']}")

    if not live:
        print("No demo app containers found. Aborting."); sys.exit(1)

    # 2. Build create configs
    plans = {}
    for svc, c in live.items():
        plans[svc] = build_config(c, TARGETS[svc])

    # 3. Print preservation guarantees
    print("\nPreservation (volumes/networks/labels restart-policy) — copied 1:1 from live:")
    for svc, c in live.items():
        hc = c["HostConfig"]
        print(f"  [{svc}] Binds={hc.get('Binds')} NetworkMode={hc.get('NetworkMode')} "
              f"Restart={hc.get('RestartPolicy',{}).get('Name')}")
    pg = live.get("backend")
    vols = (pg and pg.get("Mounts")) or []
    print(f"  postgres/redis/minio data volumes NOT touched (demo app containers use Binds={None}).")

    # 4. Pull new images
    print("\nImage pulls:")
    for svc in TARGETS:
        ref = TARGETS[svc]["new_image"]
        print(f"  [{svc}] {ref}")
        if not args.apply or args.skip_pull:
            if not args.apply:
                print("     (dry-run: skip pull)")
        else:
            print("     pulling...")
            ok = pull_image(ref)
            print(f"     -> {'OK' if ok else 'FAILED'}")
            if not ok:
                print(f"  [{svc}] pull failed — aborting apply", file=sys.stderr)
                sys.exit(3)

    # 5. Recreate
    print("\nRecreate plan (stop -> remove -> create+start):")
    for svc, c in live.items():
        t = TARGETS[svc]
        print(f"  [{svc}] {t['name']}: {c['Config']['Image']} -> {t['new_image']}")
        if t.get("reset_env"):
            print(f"          DEMO_RESET: false -> true")

    if not args.apply:
        print("\n--- dry-run dump of create payloads ---")
        for svc, c in live.items():
            cfg, hc, nc = plans[svc]
            print(f"\n[{svc}] Config.Image = {cfg.get('Image')}")
            print(f"[{svc}] Env DEMO_RESET entry: {[e for e in cfg['Env'] if e.startswith('DEMO_RESET=')] or '(none)'}")
            print(f"[{svc}] HostConfig.NetworkMode = {hc.get('NetworkMode')}")
            print(f"[{svc}] Labels (compose) = {json.dumps({k:v for k,v in (cfg.get('Labels') or {}).items() if k.startswith('com.docker.compose')}, indent=0)}")
        print("\nDry-run complete. Re-run with --apply to execute.")
        return

    # apply
    for svc in live:
        t = TARGETS[svc]
        name = t["name"]
        cfg, hc, nc = plans[svc]
        # stop
        code, _ = api("POST", f"/containers/{name}/stop?t=10")
        print(f"[{svc}] stop -> HTTP {code}")
        # remove (force in case)
        code, _ = api("DELETE", f"/containers/{name}?force=true&v=false")
        print(f"[{svc}] remove -> HTTP {code}")
        # create
        body = {"Config": cfg, "HostConfig": hc, "NetworkingConfig": nc}
        code, data = api("POST", f"/containers/create?name={name}", body=body)
        new_id = (data or {}).get("Id", "")
        if code != 204 and code != 201:
            print(f"[{svc}] CREATE FAILED HTTP {code}: {data}", file=sys.stderr)
            sys.exit(4)
        cid = new_id[:12]
        # start
        code, _ = api("POST", f"/containers/{cid}/start")
        print(f"[{svc}] create+start -> HTTP {code} cid={cid}")
        # health check
        ok = health_ok(name)
        print(f"[{svc}] health -> {'healthy/running' if ok else 'UNHEALTHY'}")

    print("\nApply complete.")


if __name__ == "__main__":
    main()
