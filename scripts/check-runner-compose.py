#!/usr/bin/env python3
"""AUT-5714: structural guard for docker-compose.runner.hosted.yml —
the git source of truth for Portainer EP5 stack 123
(gh-runner-autobrain-arm64, the single self-hosted ARM64 runner
behind build-hosted.yml).

The stack lived only inside Portainer, so nothing could catch a
hardening regression. This asserts the invariants that make the
runner survive a broker drop (AUT-5462) and an operator action:

  1. the runner image is digest-pinned and matches the digest EP5
     runs (a floating :latest silently changes broker behaviour),
  2. auto-update is disabled (an in-place self-update drifts the
     running build off the pinned digest),
  3. stop_grace_period is long enough for a build to drain
     (Docker's 10s default SIGKILLs the runner mid-job),
  4. the durable bits are wired as they are on EP5 (docker.sock,
     gh-runner-data volume, external autobrain-hosted_default
     network, unless-stopped),
  5. no literal secrets (RUNNER_TOKEN stays a stack-env
     interpolation), and
  6. the entrypoint still delegates to ./run.sh, which owns the
     signal trap the grace period protects.

Run in CI with no arguments (see .github/workflows/compose-checks.yml,
which runs every scripts/check-*.py bare; AUT-4678: guards that
nothing runs rot):
    python3 scripts/check-runner-compose.py
"""
import re
import sys

import yaml

COMPOSE = "docker-compose.runner.hosted.yml"
STACK_NAME = "gh-runner-autobrain-arm64"
SERVICE = "gh-runner-autobrain-arm64"
# The arm64 manifest EP5 runs (Runner v2.337.0), read back from
# `GET /api/endpoints/5/docker/images/{id}/json -> RepoDigests`.
# A pin that drifts here is a silent broker-behaviour change.
EXPECTED_DIGEST = (
    "ghcr.io/actions/actions-runner@"
    "sha256:e5496277be5d09bc968b3d64911b74e219ac4a3f2edce956a3ecf9271bea1ef4"
)
EXTERNAL_NETWORK = "autobrain-hosted_default"
MIN_GRACE_SECONDS = 30 * 60  # the longest hosted build must fit


def grace_seconds(value):
    """Compose duration -> seconds. Returns None when unparsable."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(s|m|h)", str(value).strip())
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2)
    return int(n * {"s": 1, "m": 60, "h": 3600}[unit])


def main():
    doc = yaml.safe_load(open(COMPOSE))
    services = doc.get("services") or {}
    problems = []

    if sorted(services) != [SERVICE]:
        problems.append(f"services are {sorted(services)}, must be exactly "
                        f"[{SERVICE!r}] (stack 123 is a single runner)")
        print("FAIL")
        for p in problems:
            print("  -", p)
        return 1

    spec = services[SERVICE]

    image = spec.get("image") or ""
    if "@sha256:" not in image:
        problems.append(f"image not digest-pinned ({image!r}) — a floating "
                        "tag lets the broker client change silently")
    elif image != EXPECTED_DIGEST:
        problems.append(f"digest pin drifted from the version EP5 runs\n"
                        f"      have {image}\n      want {EXPECTED_DIGEST}")

    env = spec.get("environment") or []
    # The compose file uses the list form. Normalise to {key: value}
    # so the guard reads either form.
    env_map = {}
    for entry in env:
        if isinstance(entry, str):
            k, _, v = entry.partition("=")
            env_map[k] = v
        else:
            env_map.update(entry)
    if env_map.get("DISABLE_AUTO_UPDATE") != "true":
        problems.append("DISABLE_AUTO_UPDATE must be true — an in-place "
                        "self-update drifts the running broker build off "
                        "the pinned digest")
    if env_map.get("EPHEMERAL") != "false":
        problems.append("EPHEMERAL must be false — the runner identity lives "
                        "in the gh-runner-data volume, not a scratch dir")
    for key, want in (("RUNNER_NAME", STACK_NAME), ("REPO_URL", None)):
        if key not in env_map:
            problems.append(f"environment is missing {key}")
    if not str(env_map.get("RUNNER_TOKEN", "")).startswith("${"):
        problems.append("RUNNER_TOKEN must be a ${RUNNER_TOKEN} stack-env "
                        "interpolation — a literal registration token in a "
                        "public repo is a leaked secret, and it expires in "
                        "an hour anyway")

    grace = grace_seconds(spec.get("stop_grace_period"))
    if grace is None:
        problems.append("stop_grace_period is missing — Docker's 10s default "
                        "SIGKILLs the runner mid-build on any stop/redeploy")
    elif grace < MIN_GRACE_SECONDS:
        problems.append(f"stop_grace_period is {spec.get('stop_grace_period')!r} "
                        f"({grace}s) — a hosted build must fit inside the "
                        f"grace, minimum {MIN_GRACE_SECONDS}s")

    if spec.get("restart") != "unless-stopped":
        problems.append("restart policy must be unless-stopped")
    if spec.get("container_name") != STACK_NAME:
        problems.append(f"container_name is {spec.get('container_name')!r}, "
                        f"must be {STACK_NAME!r}")

    mounts = spec.get("volumes") or []
    binds = [m for m in mounts if isinstance(m, str)]
    if "/var/run/docker.sock:/var/run/docker.sock" not in binds:
        problems.append("docker.sock is not bind-mounted — hosted builds "
                        "shell out to the host dockerd")
    if not any(isinstance(m, str) and m.startswith("gh-runner-data:")
               for m in binds):
        problems.append("gh-runner-data volume is not mounted at "
                        "/home/runner/_work — the runner identity (.runner) "
                        "and the workspace would not survive a recreate")

    nets = spec.get("networks") or {}
    if EXTERNAL_NETWORK not in nets:
        problems.append(f"not attached to the external {EXTERNAL_NETWORK!r} "
                        "network — the runner must reach the hosted stack")
    net = (doc.get("networks") or {}).get(EXTERNAL_NETWORK) or {}
    if not net.get("external"):
        problems.append(f"{EXTERNAL_NETWORK} is not declared external — "
                        "compose would create a second network instead of "
                        "joining the hosted stack's")

    entrypoint = spec.get("entrypoint") or []
    if "exec ./run.sh" not in " ".join(str(x) for x in entrypoint):
        problems.append("entrypoint no longer `exec ./run.sh` — run.sh owns "
                        "the signal trap that drain the in-flight job")

    if problems:
        print("FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print(f"OK: {COMPOSE} is hardened (digest-pinned, auto-update off, "
          f"stop_grace_period={spec.get('stop_grace_period')!r}, "
          f"external network {EXTERNAL_NETWORK})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
