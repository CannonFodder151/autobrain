#!/usr/bin/env bash
# Auto-cut a release when CHANGELOG.md has a non-empty [Unreleased] section.
# Runs before every app/docker build (CI + local scripts) so a shipped change
# can never land without a new version (AUT-240). Deterministic — no AI involved.
#
#   ./scripts/auto-bump.sh                # bump patch version, commit it
#   ./scripts/auto-bump.sh --no-commit    # bump files only (no git commit)
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
    commit -m "chore: release v$NEXT (auto-bump, AUT-240)" -q
  echo "==> committed v$NEXT"
fi
