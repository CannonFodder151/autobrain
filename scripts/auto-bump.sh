#!/usr/bin/env bash
# Auto-cut a release when CHANGELOG.md has a non-empty [Unreleased] section.
# Runs before every app/docker build (CI + local scripts) so a shipped change
# can never land without a new version (AUT-240). Deterministic — no AI involved.
#
#   ./scripts/auto-bump.sh                # bump patch version, commit + tag it
#   ./scripts/auto-bump.sh --no-commit    # bump files only (no git commit, no tag)
#
# Default bumps the PATCH (x.y.z -> x.y.z+1). Cut minor/major manually with
# ./scripts/bump-version.sh when a release deserves more than a patch.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMMIT=1
[[ "${1:-}" == "--no-commit" ]] && COMMIT=0

CHANGELOG=CHANGELOG.md
[[ -f "$CHANGELOG" ]] || { echo "==> no CHANGELOG.md — skipping auto-bump"; exit 0; }

# Bail if the changelog still carries unresolved merge markers (AUT-2055).
# Auto-bumping past `<<<<<<<` markers produced the stacked empty [Unreleased]
# headers and orphan bullets seen on main. Refuse to cut a release over a
# dirty changelog so a human has to resolve the conflict first.
if grep -nE '^(<<<<<<< |=======$|>>>>>>> )' "$CHANGELOG" >/dev/null; then
  echo "FAIL: $CHANGELOG has unresolved merge markers — resolve the conflict before bumping." >&2
  exit 1
fi

# Collapse duplicate empty [Unreleased] headers that an earlier run stacked.
# Keeps the FIRST [Unreleased] block (the one with content) and drops later
# empty duplicates that the awk injector leaves behind.
python3 - <<'PY'
import re, sys
p = "CHANGELOG.md"
with open(p) as f:
    lines = f.readlines()
hdr = re.compile(r'^## \[Unreleased\]')
seen = 0
out = []
for ln in lines:
    if hdr.match(ln):
        seen += 1
        if seen > 1:
            continue
    out.append(ln)
text = "".join(out)
text = re.sub(r'\n{3,}', '\n\n', text)
with open(p, 'w') as f:
    f.write(text)
PY

# Only bump if [Unreleased] has at least one bullet; an empty section is not a release.
if ! awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f && /^- /' "$CHANGELOG" | grep -q .; then
  echo "==> no unreleased changes — nothing to bump"
  exit 0
fi

CUR="$(grep -E 'APP_VERSION: str' backend/app/core/config.py | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')"
[[ "$CUR" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "FAIL: cannot parse APP_VERSION '$CUR' from backend/app/core/config.py" >&2; exit 1; }
NEXT="$(echo "$CUR" | awk -F. '{print $1"."$2"."$3+1}')"

echo "==> unreleased changes detected — cutting v$NEXT"
./scripts/bump-version.sh "$NEXT"

# Re-open an (empty) Unreleased section for the next cycle, above the release.
awk -v v="## [$NEXT] - " '
  !done && index($0, v) == 1 { print "\n## [Unreleased]\n"; done=1 }
  { print }
' "$CHANGELOG" > "$CHANGELOG.tmp" && mv "$CHANGELOG.tmp" "$CHANGELOG"

if [[ "$COMMIT" == "1" ]]; then
  git add -A
  git -c user.name="AutoBrain Release Bot" -c user.email="release@autobrainservice.app" \
    commit -m "chore: release v$NEXT (auto-bump, AUT-240) [skip ci]" -q
  echo "==> committed v$NEXT"
  # Tag the release commit so `git tag --list` and the GitHub releases API
  # can see a real v* tag instead of just a CHANGELOG line (AUT-2055).
  if git tag -l "v$NEXT" | grep -q .; then
    echo "==> tag v$NEXT already exists — skipping"
  else
    git tag -a "v$NEXT" -m "Release v$NEXT (auto-bump, AUT-2055)" HEAD
    echo "==> tagged v$NEXT"
    # Auto-push the tag if we have push access. If the push fails (shallow
    # clone, no auth), the publish workflow falls back to creating the
    # release via the GitHub API (see dockerhub-publish.yml).
    if git push origin "v$NEXT" 2>/dev/null; then
      echo "==> pushed tag v$NEXT"
    else
      echo "==> tag push failed (will be created via API in publish workflow)"
    fi
  fi
fi