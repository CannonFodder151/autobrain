#!/usr/bin/env python3
"""AUT-5669 self-check for update-compose-pins.py (stdlib + real git).

The monotonic guard is the whole point of the fix, so it is exercised
against real commits: a temp repo with two commits gives a genuine
ancestor relationship for `git merge-base --is-ancestor`.
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).with_name("update-compose-pins.py")
spec = importlib.util.spec_from_file_location("ucp", HERE)
ucp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ucp)

REPO = "ghcr.io/cannonfodder151/autobrain-backend"
BASE = f"services:\n  backend:\n    image: {REPO}:hosted@sha256:{'0' * 64}\n"
PLAIN = "services:\n  backend:\n    image: x\n"


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True)


def make_repo():
    """Temp repo with two commits so OLD is a real ancestor of NEW."""
    d = tempfile.mkdtemp(prefix="aut5669-")
    os.chdir(d)
    sh("git", "init", "-q", d)
    sh("git", "config", "user.email", "t@example.com")
    sh("git", "config", "user.name", "t")
    path = pathlib.Path("docker-compose.hosted.yml")
    path.write_text(BASE)
    sh("git", "add", ".")
    sh("git", "commit", "-q", "-m", "a")
    old = sh("git", "rev-parse", "HEAD").stdout.strip()
    path.write_text(BASE + "# second commit\n")
    sh("git", "commit", "-q", "-am", "b")
    new = sh("git", "rev-parse", "HEAD").stdout.strip()
    return d, path, old, new


D, PIN_FILE, OLD, NEW = make_repo()

# --- pin_source / set_provenance -------------------------------------------
assert ucp.pin_source(BASE) is None, "no provenance in a plain file"
stamped = ucp.set_provenance(BASE, OLD)
assert ucp.pin_source(stamped) == OLD, ucp.pin_source(stamped)
refreshed = ucp.set_provenance(stamped, NEW)
assert ucp.pin_source(refreshed) == NEW
assert len(ucp._PROV_LINE_RE.findall(refreshed)) == 1, "duplicate provenance keys"
assert REPO in refreshed and "services:" in refreshed, refreshed

# --- is_stale --------------------------------------------------------------
assert not ucp.is_stale(BASE, OLD), "unstamped file is never stale"
assert not ucp.is_stale(stamped, OLD), "same commit is not stale"
assert not ucp.is_stale(stamped, NEW), "a descendant of the owner is not stale"
assert ucp.is_stale(ucp.set_provenance(BASE, NEW), OLD), (
    "a commit older than the recorded owner must be stale")
assert not ucp.is_stale(BASE, None), "no --source-sha means no ordering claim"


def run(*args):
    sys.argv = ["update-compose-pins.py", *args]
    return ucp.main()


# a stale run must refuse (3) and leave the file byte-identical
PIN_FILE.write_text(ucp.set_provenance(BASE, NEW))
before = PIN_FILE.read_text()
assert run(f"backend=sha256:{'1' * 64}", "--source-sha", OLD) == 3, "stale run"
assert PIN_FILE.read_text() == before, "a stale run must not rewrite the file"

# the owning run rewrites the pin and stamps provenance (0)
assert run(f"backend=sha256:{'2' * 64}", "--source-sha", NEW) == 0
after = PIN_FILE.read_text()
assert "sha256:" + "2" * 64 in after, after
assert ucp.pin_source(after) == NEW, after

# same digest, same source -> nothing to commit (1), and no re-stamp noise
assert run(f"backend=sha256:{'2' * 64}", "--source-sha", NEW) == 1
assert ucp.pin_source(PIN_FILE.read_text()) == NEW

# a genuinely new digest on the owning commit still bumps
assert run(f"backend=sha256:{'3' * 64}", "--source-sha", NEW) == 0
assert "sha256:" + "3" * 64 in PIN_FILE.read_text()

# a malformed --source-sha is rejected before the file is touched
assert run(f"backend=sha256:{'4' * 64}", "--source-sha", "zzz") == 2
# a malformed digest likewise
assert run("backend=nope", "--source-sha", NEW) == 2

print("OK: update-compose-pins (monotonic guard + provenance)")
sys.exit(0)
