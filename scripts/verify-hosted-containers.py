#!/usr/bin/env python3
"""AUT-3908: verify the hosted stack on Portainer matches docker-compose.hosted.yml.

Container reduction (AUT-3153/AUT-3813) removed the standalone `worker`, `ai`/`market-data`
and `backup-agent` services. This compares the containers actually running on the endpoint
against the services declared in git, so drift or a failed re-apply fails loudly.

Run on a host with Portainer credentials:
  PORTAINER_API_KEY=<key> python3 scripts/verify-hosted-containers.py
  PORTAINER_API_KEY=<key> python3 scripts/verify-hosted-containers.py --endpoint 6 --stack autobrain-dev

Exit codes: 0 match, 1 mismatch, 2 usage/auth error.
"""
import argparse
import json
import os
import sys
import urllib.request

import yaml

COMPOSE = "docker-compose.hosted.yml"


def compose_services(path=COMPOSE):
    with open(path) as f:
        return set(yaml.safe_load(f)["services"])


def running_services(containers, stack, aliases=None):
    """Container state keyed by DECLARED service name, running or exited.

    `aliases` maps a declared service name to the sibling compose project that actually
    hosts it. On EP5 `gh-runner` runs as the standalone `gh-runner-autobrain-arm64`
    stack (single service, different label), so the project's only service is adopted
    under the declared name.
    """
    aliases = aliases or {}
    services = {}
    for c in containers:
        labels = c.get("Labels") or {}
        if labels.get("com.docker.compose.project") != stack:
            continue
        svc = labels.get("com.docker.compose.service")
        if svc:
            services[svc] = c.get("State")
    for declared, project in aliases.items():
        # ponytail: adopts the sibling project's single service; a sibling stack
        # hosting several of our services would need an explicit service mapping.
        adopted = list(_by_project(containers).get(project, {}).values())
        if len(adopted) == 1:
            services[declared] = adopted[0]
    return services


def _by_project(containers):
    out = {}
    for c in containers:
        labels = c.get("Labels") or {}
        project, svc = labels.get("com.docker.compose.project"), labels.get("com.docker.compose.service")
        if project and svc:
            out.setdefault(project, {})[svc] = c.get("State")
    return out


def compare(expected, actual):
    """-> (missing, extra) service names."""
    return sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="autobrain-hosted")
    ap.add_argument("--endpoint", type=int, default=5, help="Portainer endpoint id (5 = AutoBrain-Hosted)")
    ap.add_argument("--file", default=COMPOSE)
    ap.add_argument("--portainer-url", default=os.environ.get(
        "PORTAINER_URL", "https://portainer.nathanmartina.com"))
    ap.add_argument("--alias", action="append", default=[], metavar="SERVICE=PROJECT",
                    help="declare SERVICE as hosted by sibling compose PROJECT (repeatable)")
    args = ap.parse_args()

    aliases = {}
    for item in args.alias:
        svc, _, project = item.partition("=")
        if not svc or not project:
            print(f"ERROR: bad --alias {item!r}, expected SERVICE=PROJECT", file=sys.stderr)
            return 2
        aliases[svc] = project

    api_key = os.environ.get("PORTAINER_API_KEY")
    if not api_key:
        print("ERROR: PORTAINER_API_KEY not set", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        f"{args.portainer_url}/api/endpoints/{args.endpoint}/docker/containers/json?all=true",
        headers={"X-API-Key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            containers = json.load(r)
    except Exception as e:  # noqa: BLE001 - surface the API error verbatim
        print(f"ERROR: Portainer query failed: {e}", file=sys.stderr)
        return 2

    actual = running_services(containers, args.stack, aliases)
    expected = compose_services(args.file)
    missing, extra = compare(expected, actual)

    for svc in sorted(actual):
        print(f"  {svc:<18} {actual[svc]}")
    print(f"stack={args.stack} endpoint={args.endpoint} "
          f"compose={len(expected)} running={len(actual)}")

    not_running = [s for s, state in actual.items() if state != "running"]
    if missing or extra or not_running:
        if missing:
            print("MISSING (declared in compose, absent on endpoint): " + ", ".join(missing))
        if extra:
            print("EXTRA (running on endpoint, not in compose): " + ", ".join(extra))
        if not_running:
            print("NOT RUNNING: " + ", ".join(f"{s}({actual[s]})" for s in sorted(not_running)))
        return 1

    print(f"OK: {len(actual)} containers match {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
