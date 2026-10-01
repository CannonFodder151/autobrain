#!/usr/bin/env python3
"""AUT-3908: verify the hosted stack on Portainer matches docker-compose.hosted.yml.

Container reduction (AUT-3153/AUT-3813) removed the standalone `worker`, `ai`/`market-data`
and `backup-agent` services. This compares the containers actually running on the endpoint
against the services declared in git, so drift or a failed re-apply fails loudly.

Run on a host with Portainer credentials:
  PORTAINER_API_KEY=<key> python3 scripts/verify-hosted-containers.py
  PORTAINER_API_KEY=<key> python3 scripts/verify-hosted-containers.py --endpoint 6 --stack autobrain-dev

Companion stacks let a service that Portainer runs separately still be counted
under the name compose declares: `--companion-stack <stack>/<service>=<declared>`
(repeatable). There are no defaults — AUT-4911 dropped `gh-runner` from the
hosted compose entirely, so every declared service now runs in `--stack`.

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


# Spec format: "<stack>/<actual_service>=<declared_service>".
DEFAULT_COMPANION_STACKS: tuple = ()


def parse_companion(spec):
    """-> (stack, actual_service, declared_service) or raise ValueError."""
    try:
        stack_part, declared = spec.split("=", 1)
        stack, actual = stack_part.rsplit("/", 1)
    except ValueError:
        raise ValueError(
            f"bad --companion-stack {spec!r}; expected <stack>/<service>=<declared>"
        ) from None
    if not (stack and actual and declared):
        raise ValueError(f"bad --companion-stack {spec!r}; empty stack/service/declared")
    return stack, actual, declared


def running_services(containers, stack, companion_specs=()):
    """Declared compose service name -> state, for `stack` plus companion stacks.

    Containers are matched on their `com.docker.compose.service` label rather than
    by project membership alone, so a declared service that Portainer deployed as a
    separate stack is still seen as present. Companion entries rename the companion
    stack's service to the name the compose file declares.

    Precedence: the main stack wins, so a service running in both is not
    double-counted and companion drift cannot mask a hosted-stack failure.
    """
    # declared name -> (project, actual service) for the lookups we accept.
    lookup = {}
    for spec in companion_specs:
        cstack, actual, declared = parse_companion(spec)
        lookup[(cstack, actual)] = declared

    services = {}
    for c in containers:
        labels = c.get("Labels") or {}
        project = labels.get("com.docker.compose.project")
        actual = labels.get("com.docker.compose.service")
        if project == stack and actual:
            services[actual] = c.get("State")          # main stack wins
        elif (project, actual) in lookup:
            services.setdefault(lookup[(project, actual)], c.get("State"))
    return services


def compare(expected, actual):
    """-> (missing, extra) service names."""
    return sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="autobrain-hosted")
    ap.add_argument("--endpoint", type=int, default=5, help="Portainer endpoint id (5 = AutoBrain-Hosted)")
    ap.add_argument("--file", default=COMPOSE)
    ap.add_argument(
        "--companion-stack", action="append", dest="companion_stacks",
        default=None, metavar="STACK/SERVICE=DECLARED",
        help="Companion Portainer stack that also hosts a declared service, and "
             "how its service name maps to the declared one "
             f"(default: {', '.join(DEFAULT_COMPANION_STACKS) or 'none'}); repeatable. "
             "Pass --no-companion-stacks to count only --stack.")
    ap.add_argument("--no-companion-stacks", action="store_true",
                    help="Count only --stack; declare a service deployed as its "
                         "own stack as MISSING.")
    ap.add_argument("--portainer-url", default=os.environ.get(
        "PORTAINER_URL", "https://portainer.nathanmartina.com"))
    args = ap.parse_args()

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

    companions = ([] if args.no_companion_stacks
                  else (args.companion_stacks if args.companion_stacks is not None
                        else list(DEFAULT_COMPANION_STACKS)))
    try:
        actual = running_services(containers, args.stack, companions)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    expected = compose_services(args.file)
    missing, extra = compare(expected, actual)

    for svc in sorted(actual):
        print(f"  {svc:<18} {actual[svc]}")
    print(f"stack={args.stack} companions={';'.join(companions) or 'none'} "
          f"endpoint={args.endpoint} "
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
