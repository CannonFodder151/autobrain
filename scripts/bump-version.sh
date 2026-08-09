#!/usr/bin/env bash
# Sync the AutoBrain version everywhere in one shot so the admin banner,
# web app and changelog always track the release. Run from the repo root.
#
#   ./scripts/bump-version.sh 0.3.5
#
# Bumps: backend APP_VERSION, frontend/pubspec.yaml (increments +build),
# the AI gateway default, and promotes the CHANGELOG [Unreleased] section.
# Optionally bumps the mobile app with --mobile (autobrain-mobile is
# versioned independently):
#
#   ./scripts/bump-version.sh 0.3.5 --mobile
set -euo pipefail

V="${1:?Usage: bump-version.sh <x.y.z> [--mobile]}"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Version must be x.y.z" >&2; exit 1; }
MOBILE=0
[[ "${2:-}" == "--mobile" ]] && MOBILE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- backend APP_VERSION ---
sed -i -E "s/APP_VERSION: str = \"[0-9.]+\"/APP_VERSION: str = \"$V\"/" backend/app/core/config.py
echo "==> config.py: $(grep -E 'APP_VERSION: str' backend/app/core/config.py | head -1 | tr -s ' ')"

# --- AI gateway default (read at runtime, overridable via APP_VERSION env) ---
sed -i -E "s/os.environ.get\(\"APP_VERSION\", \"[0-9.]+\"\)/os.environ.get(\"APP_VERSION\", \"$V\")/" ai/app/main.py
echo "==> ai/app/main.py default: $(grep -E 'os.environ.get\("APP_VERSION"' ai/app/main.py | head -1)"

# --- frontend pubspec (keep +build, increment it) ---
CUR=$(grep -E '^version: ' frontend/pubspec.yaml | head -1 | awk '{print $2}')
BUILD=$(echo "$CUR" | sed -E 's/^[0-9]+\.[0-9]+\.[0-9]+\+?([0-9]*).*/\1/')
if [[ -n "$BUILD" ]]; then
  sed -i -E "s/^version: [0-9.]+.*/version: $V+$((BUILD + 1))/" frontend/pubspec.yaml
else
  sed -i -E "s/^version: .*/version: $V/" frontend/pubspec.yaml
fi
echo "==> frontend/pubspec.yaml: $(grep -E '^version:' frontend/pubspec.yaml | head -1 | awk '{print $2}')"

# --- CHANGELOG: promote [Unreleased] to a dated [V] section ---
if grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  TODAY=$(date +%Y-%m-%d)
  sed -i "0,/^## \[Unreleased\]/s//## [$V] - $TODAY/" CHANGELOG.md
  echo "==> CHANGELOG.md: promoted to [$V] - $TODAY"
fi

# --- optional mobile bump (autobrain-mobile versions independently) ---
if [[ "$MOBILE" == "1" && -f ../autobrain-mobile/pubspec.yaml ]]; then
  M=../autobrain-mobile/pubspec.yaml
  MBUILD=$(grep -E '^version: ' "$M" | head -1 | awk '{print $2}' | sed -E 's/^[0-9]+\.[0-9]+\.[0-9]+\+?([0-9]*).*/\1/')
  if [[ -n "$MBUILD" ]]; then
    sed -i -E "s/^version: [0-9.]+.*/version: $V+$((MBUILD + 1))/" "$M"
  else
    sed -i -E "s/^version: .*/version: $V/" "$M"
  fi
  echo "==> autobrain-mobile/pubspec.yaml: $(grep -E '^version:' "$M" | head -1 | awk '{print $2}')"
fi

echo
echo "==> Done — version is $V. Commit, then build & push images:"
echo "    docker build -f docker/backend/Dockerfile -t cannonfodder151/autobrain-backend:$V ./backend && docker push cannonfodder151/autobrain-backend:$V"
echo "    docker build -f docker/frontend/Dockerfile --build-arg API_BASE_URL=https://hosted.autobrainservice.app/api/v1 --build-arg WS_BASE_URL=wss://hosted.autobrainservice.app/ws -t cannonfodder151/autobrain-frontend:$V-hosted ."
echo "    docker build -f docker/frontend/Dockerfile --build-arg API_BASE_URL=https://default.autobrainservice.app/api/v1 --build-arg WS_BASE_URL=wss://default.autobrainservice.app/ws -t cannonfodder151/autobrain-frontend:$V ."
echo "    docker build -f docker/frontend/Dockerfile --build-arg API_BASE_URL=https://demo.autobrainservice.app/api/v1 --build-arg WS_BASE_URL=wss://demo.autobrainservice.app/ws -t cannonfodder151/autobrain-frontend-demo:$V ."
echo
echo "    Reminder: also add the new release to the marketing site"
echo "    (autobrainservice-website/changelog.html) — it mirrors CHANGELOG.md."
