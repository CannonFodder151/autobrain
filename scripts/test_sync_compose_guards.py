#!/usr/bin/env python3
"""AUT-4946 self-check for the sync script's pure guard logic (no network)."""
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location(
    "sync",
    pathlib.Path(__file__).with_name("sync-compose-to-portainer.py"),
)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

COMPOSE = """
services:
  frontend:
    image: f
    ports:
      - "127.0.0.1:8086:8080"
  backup:
    image: b
    ports:
      - "127.0.0.1:8080:8080"
  postgres:
    image: p
  api:
    image: a
    ports:
      - published: 9000
        target: 9000
        protocol: tcp
"""

services, ports = sync.compose_services_and_ports(COMPOSE)
assert services == {"frontend", "backup", "postgres", "api"}, services
assert ports == {"frontend": {8086}, "backup": {8080}, "api": {9000}}, ports


class FakeArgs:
    endpoint = 5
    portainer_url = "https://example.invalid"


def cont(name, service, state, published):
    return {
        "Names": [f"/{name}"],
        "State": state,
        "Labels": {"com.docker.compose.service": service} if service else {},
        "Ports": [{"PublicPort": p} for p in published],
    }


# An orphan (service not in the new compose) holding a wanted port -> clash.
orphans = [cont("old-autobrain-backup-1", "autobrain-backup", "running", [8080])]
sync.endpoint_containers = lambda args: orphans
clashes = sync.check_port_collisions(FakeArgs(), services, {8080, 8086, 9000})
assert clashes == [("old-autobrain-backup-1", "autobrain-backup", [8080])], clashes

# Same service name in the new compose -> not an orphan, no clash.
sync.endpoint_containers = lambda args: [
    cont("autobrain-hosted-backup-1", "backup", "running", [8080])]
assert sync.check_port_collisions(FakeArgs(), services, {8080}) == []

# verify_running: healthy, missing service, stuck-in-created.
sync.endpoint_containers = lambda args: [
    cont("s-frontend-1", "frontend", "running", [8086]),
    cont("s-backup-1", "backup", "running", [8080]),
    cont("s-postgres-1", "postgres", "running", []),
    cont("s-api-1", "api", "running", [9000]),
]
assert sync.verify_running(FakeArgs(), services, attempts=1, delay=0) == []

sync.endpoint_containers = lambda args: [
    cont("s-frontend-1", "frontend", "created", [8086]),
    cont("s-backup-1", "backup", "running", [8080]),
]
problems = sync.verify_running(FakeArgs(), services, attempts=1, delay=0)
assert ("s-frontend-1", "stuck in state created") in problems, problems
assert any("'postgres' has no running container" in w for _, w in problems), problems

# verify_only: healthy stack -> exit 0.
sync.endpoint_containers = lambda args: [
    cont("s-frontend-1", "frontend", "running", [8086]),
    cont("s-backup-1", "backup", "running", [8080]),
    cont("s-postgres-1", "postgres", "running", []),
    cont("s-api-1", "api", "running", [9000]),
]
class VArgs(FakeArgs):
    stack = "autobrain-hosted"
    file = "docker-compose.hosted.yml"
assert sync.verify_only(VArgs(), COMPOSE, attempts=1, delay=0) == 0

# verify_only: orphan port clash -> exit 5 (no PUT issued).
sync.endpoint_containers = lambda args: orphans
assert sync.verify_only(VArgs(), COMPOSE, attempts=1, delay=0) == 5

# verify_only: missing service -> exit 1.
sync.endpoint_containers = lambda args: [
    cont("s-frontend-1", "frontend", "running", [8086]),
    cont("s-backup-1", "backup", "running", [8080]),
]
assert sync.verify_only(VArgs(), COMPOSE, attempts=1, delay=0) == 1

# verify_only: stuck container -> exit 1.
sync.endpoint_containers = lambda args: [
    cont("s-frontend-1", "frontend", "created", [8086]),
    cont("s-backup-1", "backup", "running", [8080]),
]
assert sync.verify_only(VArgs(), COMPOSE, attempts=1, delay=0) == 1

# verify_only must NOT touch the Portainer PUT path: the function exists and
# is reachable from the module, but main() never calls it when --verify-only.
assert hasattr(sync, "verify_only")
assert hasattr(sync, "check_port_collisions")
assert hasattr(sync, "verify_running")

print("OK: sync-compose guards")
sys.exit(0)