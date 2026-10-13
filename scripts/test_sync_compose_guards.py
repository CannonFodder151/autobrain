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
    cont("s-backend-1", "backend", "running", [8080]),
]
problems = sync.verify_running(FakeArgs(), services, attempts=1, delay=0)
assert ("s-frontend-1", "stuck in state created") in problems, problems
assert any("'postgres' has no running container" in w for _, w in problems), problems

# AUT-5669: a moving tag is refused, a digest pin is not.
PINNED = """
x-autobrain-pin-source: "%s"
services:
  backend:
    image: ghcr.io/cannonfodder151/autobrain-backend:hosted@sha256:%s
"""
assert sync.unpinned_image_refs(PINNED % ("a" * 40, "b" * 64)) == {}
assert sync.unpinned_image_refs(
    "services:\n  backend:\n    image: ghcr.io/cannonfodder151/autobrain-backend:hosted\n"
) == {"backend": "ghcr.io/cannonfodder151/autobrain-backend:hosted"}
assert sync.compose_pin_source(PINNED % ("a" * 40, "b" * 64)) == "a" * 40
assert sync.compose_pin_source("services:\n  backend:\n    image: x\n") is None

# Test that recovery commands interpolate orphan container names
import io
import sys
from contextlib import redirect_stderr

class FakeArgs2:
    endpoint = 5
    portainer_url = "https://example.invalid"
    stack = "test-stack"
    create = False

# Test report() recovery output (calls verify_running internally)
sync.endpoint_containers = lambda args: [
    cont("s-frontend-1", "frontend", "created", [8086]),
    cont("s-backend-1", "backend", "running", [8080]),
]
buf = io.StringIO()
with redirect_stderr(buf):
    sync.report(FakeArgs2(), COMPOSE, services)
stderr = buf.getvalue()
assert "s-frontend-1" in stderr, f"Expected orphan container name in recovery output: {stderr}"
assert "<NAME>" not in stderr, f"Placeholder <NAME> should not appear: {stderr}"

# Test check_port_collisions recovery output (printed in main logic)
sync.endpoint_containers = lambda args: [
    cont("old-autobrain-backup-1", "autobrain-backup", "running", [8080])]
buf = io.StringIO()
with redirect_stderr(buf):
    clashes = sync.check_port_collisions(FakeArgs(), services, {8080, 8086, 9000})
    if clashes:
        print(f"ERROR: refusing to sync — host port collision with orphans on "
              f"endpoint {FakeArgs().endpoint}:", file=sys.stderr)
        for name, svc, ports in clashes:
            print(f"  {name} (service {svc!r}) holds host port(s) "
                  f"{', '.join(str(p) for p in ports)} that the new compose "
                  f"needs, but {svc!r} is not a service in the incoming compose",
                  file=sys.stderr)
        print("RECOVERY (destructive — run by hand, then re-run this sync):",
              file=sys.stderr)
        for name, svc, ports in clashes:
            print(
                f"  curl -X DELETE \"{FakeArgs().portainer_url}/api/endpoints/"
                f"{FakeArgs().endpoint}/docker/containers/{name}?force=true&v=true\" \\\n"
                f"    -H \"X-API-Key: $PORTAINER_API_KEY\"",
                file=sys.stderr)
stderr = buf.getvalue()
assert "old-autobrain-backup-1" in stderr, f"Expected orphan container name in recovery output: {stderr}"
assert "<NAME>" not in stderr, f"Placeholder <NAME> should not appear: {stderr}"

print("OK: sync-compose guards")
sys.exit(0)