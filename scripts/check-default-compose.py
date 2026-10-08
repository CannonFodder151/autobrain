#!/usr/bin/env python3
"""AUT-5611: prove docker-compose.default.yml is deployable and stays that way.

`docker compose config` is the real check, but EP2 is only reachable through the
Portainer API — no docker CLI on this box. This asserts the things that would
otherwise fail at POST /api/stacks time, plus the invariant that broke the tier
in the first place (hand-made containers: no compose labels, no network
aliases, floating tags):

  1. the Default tier's shape is intact — the three app services, the external
     `autobrain_default` network, the DNS aliases, the digest pins, and
     `scripts/upgrade-instances.sh` still resolving this stack by name, and
  2. when an env file is passed, that every ${VAR} / ${VAR:-default} /
     ${VAR:?msg} in the file resolves (deployment-time check only — the env
     holds secrets and is never committed).

Run in CI with no arguments (see .github/workflows/compose-checks.yml, which
runs every scripts/check-*.py bare; AUT-4678: guards that nothing runs rot):
    python3 scripts/check-default-compose.py
Run before deploying a real stack:
    python3 scripts/check-default-compose.py docker-compose.default.yml .env
"""
import os
import re
import sys

import yaml

VARS = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?])?([^}]*)\}")

COMPOSE = "docker-compose.default.yml"
STACK_NAME = "autobrain-default"
UPGRADE_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "scripts", "upgrade-instances.sh")
SERVICES = ("ai", "backend", "frontend")
# The digests EP2 ran as hand-made containers, read back from
# `GET /docker/images/{id}/json -> RepoDigests` and matched to each running
# container's ImageID. A pin that drifts here is a silent version change into
# the tier, which is the bug this file exists to prevent.
EXPECTED_DIGESTS = {
    "ai": "cannonfodder151/autobrain-ai@sha256:03656882722b9fb140c48a2536e97ddd5b054e4660c284bcd3abddfd30d2a527",
    "backend": "cannonfodder151/autobrain-backend@sha256:63ff74f9a66f7ec449d2c2fc7e71a125e48a6430079f06310aed0dfc3087f93a",
    "frontend": "cannonfodder151/autobrain-frontend@sha256:c4aee40082273f63d287cd2398fc650f58c11c96fa14ebae3c82851fab6003a4",
}
# The DNS names the tier resolves on the shared network. backend had none.
EXTERNAL_NETWORK = "autobrain_default"


def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k] = v
    return env


def main():
    compose_path = sys.argv[1] if len(sys.argv) > 1 else COMPOSE
    env_path = sys.argv[2] if len(sys.argv) > 2 else None
    text = open(compose_path).read()
    doc = yaml.safe_load(text)
    services = doc.get("services") or {}
    problems = []

    # 1. interpolation — only checkable with a real (uncommitted) env file.
    env = {}
    if env_path:
        env = load_env(env_path)
        for name, op, arg in VARS.findall(text):
            mode = op[1:] if op.startswith(":") else op
            if name in env and env[name] != "":
                continue
            if mode == "-":
                continue        # any default (even empty) covers unset
            # mode "?" (required) and "" (bare ${VAR}) both fail unset.
            problems.append(f"${{{name}}} is not set in {env_path}")

    # 2. shape the Default tier depends on
    if sorted(services) != sorted(SERVICES):
        problems.append(f"services are {sorted(services)}, must be exactly "
                        f"{sorted(SERVICES)} (postgres/redis/minio belong to "
                        "the /opt/autobrain-default compose project)")

    for svc, spec in services.items():
        image = spec.get("image") or ""
        if "@sha256:" not in image:
            problems.append(f"{svc}: image not digest-pinned ({image!r})")
        elif EXPECTED_DIGESTS.get(svc) and image != EXPECTED_DIGESTS[svc]:
            problems.append(f"{svc}: digest pin drifted from the version EP2 runs\n"
                            f"      have {image}\n      want {EXPECTED_DIGESTS[svc]}")
        if spec.get("restart") != "unless-stopped":
            problems.append(f"{svc}: restart policy must be unless-stopped")
        if not spec.get("healthcheck"):
            problems.append(f"{svc}: no healthcheck")
        # The AUT-5611 invariant: every service publishes its name on the
        # shared network, so any recreate (watchtower, hand, stack) resolves.
        nets = spec.get("networks") or {}
        if "default" not in nets:
            problems.append(f"{svc}: not attached to the default network")
        elif svc not in (nets["default"] or {}).get("aliases", []):
            problems.append(f"{svc}: no explicit '{svc}' network alias")

    # 3. the network itself: external, and named after the infra project.
    net = (doc.get("networks") or {}).get("default") or {}
    if not net.get("external"):
        problems.append("default network is not external — compose would create "
                        f"a second network instead of joining {EXTERNAL_NETWORK}")
    if net.get("name") != EXTERNAL_NETWORK:
        problems.append(f"default network is named {net.get('name')!r}, must be "
                        f"{EXTERNAL_NETWORK!r}")

    # 4. service-name addressing the containers depend on at runtime
    backend_env = services.get("backend", {}).get("environment") or {}
    for host, key in (("postgres", "POSTGRES_HOST"), ("redis", "REDIS_URL"),
                      ("minio", "MINIO_ENDPOINT"), ("ai", "AI_LOCAL_BASE_URL")):
        if host not in str(backend_env.get(key)):
            problems.append(f"backend does not address {host!r} by service name")
    frontend_env = services.get("frontend", {}).get("environment") or {}
    if "backend:8000" not in str(frontend_env.get("BACKEND_URL")):
        problems.append("frontend BACKEND_URL does not address backend by service name")
    if not any("8088:8080" in str(p) for p in services.get("frontend", {}).get("ports") or []):
        problems.append("frontend does not publish host 8088 (Default vhost upstream)")

    # 5. project name: must be the Portainer stack name that
    # scripts/upgrade-instances.sh resolves, and must NOT be `autobrain`,
    # whose compose project namespace holds the Default database.
    if doc.get("name") != STACK_NAME:
        problems.append(f"project name is {doc.get('name')!r}, must be {STACK_NAME!r}")
    tier_line = f"{STACK_NAME}|2|https://default.autobrainservice.app/health|"
    if os.path.exists(UPGRADE_SCRIPT):
        if tier_line not in open(UPGRADE_SCRIPT).read():
            problems.append("upgrade-instances.sh DEFAULT_TIERS no longer resolves "
                            f"this stack ({STACK_NAME} on EP2) — the Default tier "
                            "would be skipped by the promotion path")

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
    scope = f", {len(env)} env keys resolved" if env_path else ", interpolation check skipped (no env file)"
    print(f"OK: {compose_path} is deployable ({len(services)} services, "
          f"external network {EXTERNAL_NETWORK}, aliases present, digests "
          f"pinned{scope})")
    return 0


if __name__ == "__main__":
    sys.exit(main())