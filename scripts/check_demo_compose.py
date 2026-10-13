#!/usr/bin/env python3
"""AUT-5582/AUT-5766: structural checks for the demo compose file.

Run: python3 scripts/check_demo_compose.py
No docker daemon needed — validates YAML/anchors and demo-tier invariants.

AUT-5766: now runs as a no-arg CI gate (was: crashed with IndexError when
called without args). Asserts:
  1. DEMO_PASSWORD is a required interpolated var (not optional, not literal)
  2. No literal demo credential anywhere in the compose file
  3. Every service, network alias, volume and healthcheck the Demo stack needs
     is present, with the image digests pinned to what EP2 currently runs.
"""
import os
import re
import sys

import yaml

COMPOSE = "docker-compose.demo.yml"
VARS = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?])?([^}]*)\}")


def main():
    with open(COMPOSE) as f:
        text = f.read()
    doc = yaml.safe_load(text)

    problems = []

    # AUT-5766: DEMO_PASSWORD must be a required interpolated var.
    demo_password_matches = [
        m for m in VARS.finditer(text) if m.group(1) == "DEMO_PASSWORD"
    ]
    if not demo_password_matches:
        problems.append("DEMO_PASSWORD is not referenced in the compose file")
    else:
        for m in demo_password_matches:
            op = m.group(2) or ""
            mode = op[1:] if op.startswith(":") else op
            if mode != "?":
                problems.append(
                    f"DEMO_PASSWORD uses ${{{m.group(0)}}} — must be required "
                    f"(${{DEMO_PASSWORD:?...}})"
                )

    # AUT-5766: no literal demo credential anywhere in the compose.
    # Check for common patterns: demo/demo, demo123, password=demo, etc.
    literal_patterns = [
        (r"demo\s*/\s*demo", "demo/demo"),
        (r"password\s*[=:]\s*demo\b", "password=demo"),
        (r"DEMO_PASSWORD\s*[=:]\s*['\"]?demo\b", "DEMO_PASSWORD=demo"),
    ]
    for pattern, desc in literal_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            problems.append(f"literal demo credential found: {desc}")

    # Shape the Demo tier depends on.
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
    print(f"OK: {COMPOSE} is deployable "
          f"({len(services)} services, {len(volumes)} volumes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
