#!/usr/bin/env bash
# AUT-5669: compose/k8s pin bumps must be monotonic in commit order.
#
# build-hosted.yml runs every push to main under
# `concurrency: {group: build-hosted, cancel-in-progress: false}`,
# so runs QUEUE rather than cancel. A run queued behind a slow
# ~20 min multi-arch build finishes AFTER a run for a newer commit,
# and its compose-pin/k8s-pin job then overwrites the pins with a
# manifest older than the one already pinned — the last writer is
# not the newest commit. Measured 2026-10-05T03:25Z (AUT-5669):
# three different frontend digests live at once (EP5, :hosted tag,
# main compose pin).
#
# Every pin-bump commit now carries its build SHA in its message
# ("build-sha <40-hex>"), so the SHA that produced the currently
# pinned digests is discoverable from git history alone. This guard
# no-ops a bump whose build SHA is a strict ancestor of that SHA,
# i.e. a run that is older than the newest already-pinned build.
#
# Usage: guard-compose-pin-monotonic.sh <build-sha> <git-paths>...
# Exit 0 = fresh (proceed with the bump); exit 1 = stale (skip).
set -euo pipefail

current_sha="${1:?usage: guard-compose-pin-monotonic.sh <build-sha> <git-paths...>}"
shift
paths=("$@")

# Most recent pin-bump commit touching these paths, and the build
# SHA it recorded. --grep keeps auto-bump/version commits (whose
# messages never carry "build-sha") out of the result. `|| true`
# because git log exits 1 when no commit matches yet.
last_bump_sha="$(git log -1 --format=%B --grep='build-sha' -- "${paths[@]}" \
  | grep -oE 'build-sha [0-9a-f]{40}' | head -n1 | awk '{print $2}' || true)"

if [ -n "$last_bump_sha" ] \
   && [ "$last_bump_sha" != "$current_sha" ] \
   && git merge-base --is-ancestor "$current_sha" "$last_bump_sha"; then
  echo "STALE build=$current_sha last_bump=$last_bump_sha — pins already bumped by a newer build; skipping"
  exit 1
fi

echo "FRESH build=$current_sha last_bump=${last_bump_sha:-none} — proceeding with pin bump"
