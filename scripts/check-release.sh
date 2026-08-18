#!/usr/bin/env bash
# Fail a release if the changelog and app version are out of sync (AUT-148).
# Called by deploy.sh and publish-images.sh; can be run standalone.
# Usage: ./scripts/check-release.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ERR=0

TOP_CHANGELOG=$(grep -m1 '^## \[' CHANGELOG.md | sed -E 's/^## \[([^]]+)\].*/\1/')
if [[ "$TOP_CHANGELOG" == "Unreleased" ]]; then
  if awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f && /^- /' CHANGELOG.md | grep -q .; then
    echo "FAIL: CHANGELOG.md has unreleased changes under [Unreleased] — run ./scripts/bump-version.sh <x.y.z> before deploying." >&2
    ERR=1
  fi
fi

APP_VERSION=$(grep -E 'APP_VERSION: str' backend/app/core/config.py | sed -E 's/.*"([0-9.]+)".*/\1/')
if [[ "$TOP_CHANGELOG" != "Unreleased" && "$APP_VERSION" != "$TOP_CHANGELOG" ]]; then
  echo "FAIL: APP_VERSION ($APP_VERSION) != top changelog version ($TOP_CHANGELOG). Re-run ./scripts/bump-version.sh." >&2
  ERR=1
fi

if [[ "$ERR" != "0" ]]; then
  echo "==> Release check FAILED. Fix the version/changelog mismatch first (AUT-148)." >&2
  exit 1
fi

if [[ "$TOP_CHANGELOG" == "Unreleased" ]]; then
  echo "==> Release check OK: [Unreleased] is empty, APP_VERSION ($APP_VERSION) ready for release."
else
  echo "==> Release check OK: changelog promoted to [$TOP_CHANGELOG] and APP_VERSION matches."
fi
