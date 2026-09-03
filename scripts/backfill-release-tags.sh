#!/usr/bin/env bash
# Backfill missing v* git tags for autobrain releases that auto-bump committed
# without tagging (root cause AUT-2055). One-shot — safe to delete after the
# first run.
#
#   ./scripts/backfill-release-tags.sh [--create-releases]
#
# Walks main, finds every "chore: release vX.Y.Z (auto-bump, AUT-240) [skip ci]"
# commit, and creates the vX.Y.Z tag locally + pushes it. Tags already on the
# remote are skipped. Pass --create-releases to also create a GitHub Release
# for each new tag using the matching CHANGELOG.md section as the body.
#
# Idempotent: re-running it after a partial failure just no-ops the tags that
# already exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CREATE_RELEASES=0
[[ "${1:-}" == "--create-releases" ]] && CREATE_RELEASES=1

DRY_RUN=1
[[ "${BACKFILL_APPLY:-}" == "1" ]] && DRY_RUN=0

if [[ "$DRY_RUN" == "1" ]]; then
  echo "==> DRY RUN — set BACKFILL_APPLY=1 to push/create"
fi

# Map every chore:release vX.Y.Z commit to its SHA + version
# Each line is "<sha> <subject>"; the subject starts with "chore: release vX.Y.Z".
# Pull the version out by regex so older commits without "[skip ci]" still match.
COMMITS="$(git log --format='%H %s' HEAD 2>/dev/null | \
  grep -E '^[^ ]+ chore: release v[0-9]+\.[0-9]+\.[0-9]+( |$)' | \
  awk '{ sha=$1; sub(/^[^ ]+ chore: release v/, "", $0); sub(/ .*/, "", $0); print sha " " $0 }')"

if [[ -z "$COMMITS" ]]; then
  echo "==> no auto-bump release commits found on origin/main"
  exit 0
fi

# Batch-fetch all remote v* tags once (avoid N round trips)
REMOTE_TAGS="$(mktemp)"
trap 'rm -f "$REMOTE_TAGS"' EXIT
if [[ "$DRY_RUN" == "0" ]]; then
  git ls-remote --tags origin 2>/dev/null \
    | awk '{print $2}' | sed 's#refs/tags/##' > "$REMOTE_TAGS" || true
else
  : > "$REMOTE_TAGS"
fi

CREATED=0
SKIPPED=0
FAILED=0

while IFS= read -r line; do
  sha="$(awk '{print $1}' <<<"$line")"
  ver="$(awk '{print $2}' <<<"$line")"
  tag="v$ver"
  if git rev-parse "$tag" >/dev/null 2>&1; then
    echo "skip $tag — exists locally"
    SKIPPED=$((SKIPPED+1))
    continue
  fi
  if grep -Fxq "$tag" "$REMOTE_TAGS"; then
    echo "skip $tag — exists on origin"
    SKIPPED=$((SKIPPED+1))
    continue
  fi
  echo "tag $tag @ ${sha:0:7}"
  if [[ "$DRY_RUN" == "0" ]]; then
    if git tag -a "$tag" -m "Release $tag (backfilled, AUT-2055)" "$sha"; then
      if git push origin "$tag" 2>/dev/null; then
        CREATED=$((CREATED+1))
      else
        echo "  tag push failed for $tag"
        FAILED=$((FAILED+1))
      fi
    else
      echo "  git tag failed for $tag"
      FAILED=$((FAILED+1))
    fi
  else
    CREATED=$((CREATED+1))
  fi
done <<<"$COMMITS"

echo "==> summary: would_create=$CREATED skipped=$SKIPPED failed=$FAILED"

if [[ "$CREATE_RELEASES" == "1" && "$DRY_RUN" == "0" && "$CREATED" -gt 0 ]]; then
  echo "==> creating GitHub Releases for new tags..."
  while IFS= read -r line; do
    sha="$(awk '{print $1}' <<<"$line")"
    ver="$(awk '{print $2}' <<<"$line")"
    tag="v$ver"
    # Skip tags that don't exist on origin (we just created them above)
    if ! grep -Fxq "$tag" "$REMOTE_TAGS"; then
      continue
    fi
    # Body: CHANGELOG section for this version, or empty fallback
    body="$(awk -v v="## [$ver] - " '
      $0 ~ "^"v { f=1; next }
      /^## \[/ { f=0 }
      f { print }
    ' CHANGELOG.md | sed '/./,$!d' | sed -e :a -e '/^$/N;/\n$/ba' -e 'P;D' || true)"
    if [[ -z "$body" ]]; then
      body="Backfilled release tag (AUT-2055). See CHANGELOG.md for the section."
    fi
    gh release create "$tag" \
      --repo "$GITHUB_REPOSITORY" \
      --title "Release $tag" \
      --notes "$body" \
      --target "$sha" 2>&1 | head -2 || true
  done <<<"$COMMITS"
fi