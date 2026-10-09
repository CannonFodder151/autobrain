#!/usr/bin/env python3
"""AUT-5690: the Discord incident fallback must never die in curl's option parser.

Run: python3 scripts/check-discord-webhook-guard.py
No network, no docker daemon — every check is local.

A workflow secret that is not an http(s) URL reaches `curl "$DISCORD_REPORT_WEBHOOK"`
as an *option* instead of a URL, and curl exits 2 with
`curl: option -: is unknown`. The alert then silently never sent, so a lost CI
triage wake stayed invisible even though PR #924 made that wake fail loudly.

This guard asserts, for every workflow that posts to the n8n Discord Reporter:
  1. the YAML parses and every `run:` block is valid bash (`bash -n`);
  2. the secret is copied into a `discord_url` local and passed through a
     `case` that only admits `https://*` / `http://*` before curl sees it;
  3. no curl invocation still uses the raw `$DISCORD_REPORT_WEBHOOK`;
  4. the *real* guard text, lifted out of the workflow, is exercised against a
     table of good and bad secret values (empty, leading dash, bare flag,
     relative path, scheme-less host) with the expected exit code.

Exit code 0 = all invariants hold; 1 = at least one is broken.
"""

import re
import subprocess
import sys
import tempfile
import os

import yaml

# workflow -> (step name that posts to Discord, expected guard exit on a BAD value)
# `ci-triage-webhook.yml` already fails the step, so the guard exits 1.
# `libexpat-version-check.yml` runs `if: always()`, so the guard must exit 0
# to keep a green run green (AUT-5574).
TARGETS = [
    (".github/workflows/ci-triage-webhook.yml", 1),
    (".github/workflows/libexpat-version-check.yml", 0),
]

GOOD_SECRETS = [
    "https://n8n.nathanmartina.com/webhook/discord-report",
    "http://example.invalid/hook",
]
BAD_SECRETS = [
    "",
    "-",
    "--connect-timeout",
    "webhook/discord-report",
    "n8n.nathanmartina.com/webhook",
    "mailto:ops@autobrainservice.app",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    globals()["_failed"] = True


_failed = False


def run_blocks(path: str):
    doc = yaml.safe_load(open(path))
    for job_name, job in doc["jobs"].items():
        for step in job["steps"]:
            if "run" in step:
                yield f"{path}::{job_name}::{step.get('name')}", step["run"]


def check_bash_n(path: str) -> None:
    for label, run in run_blocks(path):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(run)
            tmp = fh.name
        try:
            res = subprocess.run(["bash", "-n", tmp], capture_output=True, text=True)
        finally:
            os.unlink(tmp)
        if res.returncode != 0:
            fail(f"{label} does not pass `bash -n`: {res.stderr.strip()}")


def check_guard_text(path: str) -> None:
    src = open(path).read()
    if not re.search(r'discord_url="\$\{DISCORD_REPORT_WEBHOOK:-\}"', src):
        fail(f"{path}: no `discord_url=${{DISCORD_REPORT_WEBHOOK:-}}` local")
    if not re.search(
        r"case \"\$discord_url\" in\s*\n\s*https://\*\|http://\*\) ;;", src
    ):
        fail(f"{path}: no http(s)-only `case` guard over `$discord_url`")
    # curl must post to the guarded local, never to the raw secret.
    if re.search(r'curl .*"\$DISCORD_REPORT_WEBHOOK"', src):
        fail(f"{path}: a curl still uses the raw `$DISCORD_REPORT_WEBHOOK`")
    if not re.search(r'curl .*"\$discord_url"', src):
        fail(f"{path}: no curl posting to the guarded `$discord_url`")


def lift_guard(path: str) -> str:
    """Pull the `discord_url=` + `case ... esac` block out of the workflow."""
    src = open(path).read()
    match = re.search(
        r'( *)discord_url="\$\{DISCORD_REPORT_WEBHOOK:-\}"\n\1case .*?\n\1esac\n',
        src,
        re.S,
    )
    if not match:
        fail(f"{path}: could not lift the guard block")
        return ""
    return match.group(0)


def exercise_guard(path: str, bad_exit: int) -> None:
    guard = lift_guard(path)
    if not guard:
        return
    for secret in GOOD_SECRETS:
        res = _run_guard(guard, secret)
        if res.returncode != 0:
            fail(f"{path}: guard rejected a VALID secret {secret!r} (rc={res.returncode}): {res.stderr.strip()}")
    for secret in BAD_SECRETS:
        res = _run_guard(guard, secret)
        if res.returncode != bad_exit:
            fail(
                f"{path}: guard let a MALFORMED secret {secret!r} through "
                f"(rc={res.returncode}, wanted {bad_exit}): {res.stderr.strip()}"
            )


def _run_guard(guard: str, secret: str):
    env = dict(os.environ, DISCORD_REPORT_WEBHOOK=secret)
    script = f"set -uo pipefail\n{guard}\necho GUARD_PASSED\n"
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)


for workflow, bad_exit in TARGETS:
    if not os.path.exists(workflow):
        fail(f"{workflow} is missing")
        continue
    check_bash_n(workflow)
    check_guard_text(workflow)
    exercise_guard(workflow, bad_exit)

if _failed:
    print("\ncheck-discord-webhook-guard: FAILED")
    sys.exit(1)
print("check-discord-webhook-guard: ok")
