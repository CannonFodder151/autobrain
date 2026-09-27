#!/usr/bin/env bash
# AUT-1029: skip a queued main-branch run when a newer main commit has
# already succeeded or is running/queued. Never cancels an in-flight run
# (AUT-967/AUT-1756); the superseded run exits cheaply instead of rebuilding.
set -euo pipefail

workflow_file="$1"
current_sha="$2"
repo="${GITHUB_REPOSITORY}"
token="${GITHUB_TOKEN:?GITHUB_TOKEN must be set}"

# Find newer runs on main for this workflow that are not cancelled/skipped.
# Query in created_at DESC order (newest first).
newer_sha=$(gh api \
  "repos/${repo}/actions/workflows/${workflow_file}/runs?branch=main&per_page=30" \
  --jq "
    .workflow_runs[]
    | select(.head_sha != \"${current_sha}\" and .conclusion != \"cancelled\" and .conclusion != \"skipped\")
    | .head_sha
  " | head -1)

[ -z "$newer_sha" ] && { echo "no newer run — proceed"; exit 0; }

# If the newer SHA is a descendant of our SHA (our code is ancestor of newer),
# our run adds no value — the newer run will publish the superset.
# Use GitHub's compare endpoint: if our SHA is base and newer is head,
# status "ahead" means newer contains ours.
status=$(gh api "repos/${repo}/compare/${current_sha}...${newer_sha}" --jq .status 2>/dev/null || echo "error")
if [ "$status" = "ahead" ]; then
  echo "superseded: newer run $newer_sha is ahead of $current_sha — skipping"
  exit 1
fi

echo "newer run exists but not a descendant ($status) — proceed"
exit 0