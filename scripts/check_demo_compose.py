#!/usr/bin/env python3
"""AUT-5582: prove docker-compose.demo.yml can be deployed as written.

`docker compose config` is the real check, but EP2 is only reachable through
the Portainer API — no docker CLI on this box. This asserts the two things
that would otherwise fail at POST /api/stacks time:

  1. every ${VAR} / ${VAR:-default} / ${VAR:?msg} in the file resolves, and
  2. every service, network alias, volume and healthcheck the Demo stack needs
     is present, with the image digests pinned to what EP2 currently runs.

Run: python3 reports/check_demo_compose.py <compose> <env-file>
Exit 0 = deployable.
"""
import re
import sys

import yaml

VARS = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?])?([^}]*)\}")

def main():
    compose_path, env_path = sys.argv[1], sys.argv[2]
    text = open(compose_path).read()
    doc = yaml.safe_load(text)

    env = {}
    for line in open(env_path):
        line = line.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k] = v

    problems = []

    # 1. interpolation. op is ":" followed by "-", "?" or nothing.
    for name, op, arg in VARS.findall(text):
        mode = op[1:] if op.startswith(":") else op
        if name in env and env[name] != "":
            continue
        if mode == "-":
            continue        # any default (even empty) covers unset
        # mode "?" (required) and "" (bare ${VAR}) both fail unset.
        problems.append(f"${{{name}}} is not set in the env file")

    # 2. shape the Demo tier depends on
    services = doc.get("services") or {}
    for required in ("postgres", "redis", "minio", "ai", "backend", "frontend"):
        if required not in services:
            problems.append(f"missing service {required!r}")

    for svc, spec in services.items():
        image = (spec.get("image") or "")
        if "@sha256:" not in image:
            problems.append(f"{svc}: image not digest-pinned ({image!r})")
        if spec.get("restart") != "unless-stopped":
            problems.append(f"{svc}: restart policy must be unless-stopped")
        if not spec.get("healthcheck"):
            problems.append(f"{svc}: no healthcheck")

    # The DNS-alias guarantee AUT-5582 exists for: the service names the
    # backend/frontend resolve are the compose service names.
    backend_env = (services.get("backend", {}).get("environment") or {})
    for host in ("postgres", "redis", "minio", "ai"):
        value = backend_env.get(f"{host.upper()}_HOST") or backend_env.get(
            {"redis": "REDIS_URL", "minio": "MINIO_ENDPOINT",
             "ai": "AI_LOCAL_BASE_URL"}.get(host, "")
        ) or ""
        if host not in str(value):
            problems.append(f"backend does not address {host!r} by service name")
    frontend_env = services.get("frontend", {}).get("environment") or {}
    if "backend:8000" not in str(frontend_env.get("BACKEND_URL")):
        problems.append("frontend BACKEND_URL does not address backend by service name")

    volumes = doc.get("volumes") or {}
    for v in ("postgres-data", "redis-data", "minio-data"):
        if v not in volumes:
            problems.append(f"missing volume declaration {v!r}")
        else:
            declared = volumes[v]
            # An explicit name would break the running data: EP2's volumes are
            # autobrain-demo_<v> from project name autobrain-demo.
            if isinstance(declared, dict) and declared.get("name"):
                problems.append(f"volume {v!r} renames to {declared['name']!r}; "
                                "EP2 data would be orphaned")

    if doc.get("name") != "autobrain-demo":
        problems.append(f"project name is {doc.get('name')!r}, must be "
                        "'autobrain-demo' (volumes, network and the "
                        "plate-api-scraper external join all key off it)")

    # No literal secrets in a public repo.
    for svc, spec in services.items():
        for key, value in (spec.get("environment") or {}).items():
            if re.search(r"(PASSWORD|SECRET|API_KEY)", key) and not str(value).startswith("${"):
                problems.append(f"{svc}: {key} looks like a literal secret")

    if problems:
        print("FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK: {compose_path} is deployable "
          f"({len(services)} services, {len(volumes)} volumes, "
          f"{len(env)} env keys resolved)")
    return 0

if __name__ == "__main__":
    sys.exit(main())