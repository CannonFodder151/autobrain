#!/usr/bin/env python3
"""AUT-1964: preventive CI env-var check.

Every env-var interpolation referenced by any docker-compose*.yml must be
declared in .env.example so operators know where to set it before deploy.

Required vars (no default, or `${VAR:?...}`) MUST be declared.
Optional vars (`${VAR:-...}`) are documented but not blocking — they have a
safe default at deploy time.

Skips:
  - comment lines (starting with #)
  - `$${VAR}` — shell-escaped `$` inside `command:` strings

Exits non-zero if any REQUIRED var is missing from .env.example.
"""
import re, pathlib, sys

COMPOSE_GLOB = "docker-compose*.yml"
envex = set()
for line in pathlib.Path(".env.example").read_text().splitlines():
    if not line.strip() or line.strip().startswith("#"):
        continue
    envex.add(line.split("=", 1)[0].strip())

required = set()   # (file, key) — no default, or :?
optional = set()   # (file, key) — has :- default
for p in sorted(pathlib.Path(".").glob(COMPOSE_GLOB)):
    text = p.read_text()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0]  # strip trailing comments
        # skip shell-escaped $${VAR} (literal $$ in command: strings)
        line = line.replace("$${", "\x00")
        for m in re.finditer(r"\$\{([A-Z][A-Z0-9_]*)(:-|:\?)?", line):
            key = m.group(1)
            suffix = m.group(2)
            if suffix == ":-":
                optional.add((p.name, key))
            else:
                required.add((p.name, key))

missing = sorted(k for k in required if k[1] not in envex)
if missing:
    print("FAIL: required env vars (no default / :?) missing from .env.example (AUT-1964):")
    for f, k in missing:
        print(f"  {f}: {k}")
    print()
    print("Optional vars with defaults (non-blocking):")
    for f, k in sorted(optional):
        if k not in envex:
            print(f"  {f}: {k}")
    sys.exit(1)

print(f"OK: all required env vars declared in .env.example (AUT-1964).")
print(f"    {len(required)} required, {len(optional)} optional (with defaults).")
