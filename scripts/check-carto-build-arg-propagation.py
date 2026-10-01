#!/usr/bin/env python3
"""AUT-4824: every documented/scripted frontend build path passes CARTO_API_KEY.

Since AUT-4690 `docker/frontend/Dockerfile` hard-fails when CARTO_API_KEY is
unset. Any `docker build -f docker/frontend/Dockerfile` snippet in docs or
scripts that omits `--build-arg CARTO_API_KEY` is therefore broken if copied.

Run: python3 scripts/check-carto-build-arg-propagation.py
No docker daemon needed — static scan only.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND_DF = "docker/frontend/Dockerfile"
BUILD_RE = re.compile(r"docker\s+build(?:x)?\b[^\n]*" + re.escape(FRONTEND_DF))
# splitlines() already removed the newline, so a trailing backslash is the cue.
CONT_RE = re.compile(r"\\\s*$")
LINE_CONT = re.compile(r"\s*\\\s*")


def build_commands(text: str):
    """Yield (line_no, full_command) for every frontend docker build invocation.

    Joins backslash-continued lines so multi-line snippets are checked whole.
    """
    lines = text.splitlines()
    joined, buf, start = [], [], 0
    for i, line in enumerate(lines, 1):
        if buf:
            buf.append(line)
        elif BUILD_RE.search(line):
            buf, start = [line], i
        if buf and CONT_RE.search(line):
            continue
        if buf:
            joined.append((start, LINE_CONT.sub(" ", "\n".join(buf))))
            buf = []
    return joined


def main() -> int:
    # Guard: the Dockerfile must actually still hard-fail, or this check is vacuous.
    df = (ROOT / FRONTEND_DF).read_text()
    if "ARG CARTO_API_KEY=" not in df or "-n \"${CARTO_API_KEY}\"" not in df:
        print(f"FAIL: {FRONTEND_DF} no longer hard-fails on an empty CARTO_API_KEY")
        return 1

    targets = sorted(
        [p for p in (ROOT / "docs").rglob("*.md")]
        + [p for p in (ROOT / "scripts").rglob("*.sh")]
        + [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
    )
    targets = [p for p in targets if p.is_file()]

    bad = []
    for path in targets:
        for line_no, cmd in build_commands(path.read_text()):
            if "CARTO_API_KEY" not in cmd:
                rel = path.relative_to(ROOT)
                bad.append(f"{rel}:{line_no}  {cmd.strip()}")

    if bad:
        print(f"FAIL: {len(bad)} frontend build path(s) omit --build-arg CARTO_API_KEY:")
        for b in bad:
            print(f"  {b}")
        return 1

    print(f"PASS: every documented/scripted {FRONTEND_DF} build passes CARTO_API_KEY")
    return 0


if __name__ == "__main__":
    sys.exit(main())