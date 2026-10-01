#!/usr/bin/env bash
# AUT-1720 + AUT-4949: free queued workflow runs that are dead weight on the
# self-hosted runner fleet.
#
# Three classes are cancelled:
#   1. deleted/merged head branch  — unstartable zombie (original AUT-1720 case)
#   2. superseded push/dispatch    — a newer run of the same workflow on the same
#                                    ref is already queued/in progress, so this one
#                                    can only ever publish a stale artifact
#   3. starved                     — queued past a wall-clock ceiling on a busy
#                                    fleet, so it will never be picked up
#
# Invariants: never touch in-flight runs (only `queued` is listed), never touch this
# guard's own ticks, and never cancel the newest queued run of a (workflow, ref)
# except via the starvation ceiling.
#
# Test doubles (all optional, all read from env):
#   QUEUED_RUNS_FILE  — TSV of id/created_at/event/branch/name/sha instead of the API
#   LIVE_BRANCHES_FILE— one branch per line instead of `git ls-remote`
#   DRY_RUN=1         — report the decision, do not call the API
#   NOW_EPOCH         — freeze "now" for deterministic age math in tests
set -euo pipefail

repo="${1:?usage: ci-queue-guard.sh <repo>}"
# NOW_EPOCH is a test seam so fixture timestamps are deterministic.
now=${NOW_EPOCH:-$(date -u +%s)}
push_ttl="${PUSH_TTL_MINUTES:-45}"
pr_ttl="${PR_TTL_MINUTES:-240}"

cancel() {
  local id="$1" why="$2"
  if [ "${DRY_RUN:-0}" = 1 ]; then
    echo "run $id: WOULD CANCEL ($why)"
    return 0
  fi
  if gh api -X POST "repos/CannonFodder151/$repo/actions/runs/$id/cancel" >/dev/null 2>&1; then
    echo "run $id: cancelled ($why)"
  else
    echo "run $id: cancel unavailable (GH zombie) — will retry next tick"
  fi
}

branch_exists() {
  if [ -n "${LIVE_BRANCHES_FILE:-}" ]; then
    grep -qxF "$1" "$LIVE_BRANCHES_FILE"
    return
  fi
  git ls-remote --heads --exit-code \
    "https://github.com/CannonFodder151/$repo.git" "$1" >/dev/null 2>&1
}

age_min() { echo $(( (now - $(date -u -d "$1" +%s)) / 60 )); }

# Oldest first, so the "newest per (workflow, ref)" pass below keeps the run that
# is actually ahead.
if [ -n "${QUEUED_RUNS_FILE:-}" ]; then
  runs=$(sort -t$'\t' -k2,2 "$QUEUED_RUNS_FILE")
else
  runs=$(gh api "repos/CannonFodder151/$repo/actions/runs?status=queued&per_page=100" \
           --jq '.workflow_runs[]
                 | "\(.id)\t\(.created_at)\t\(.event)\t\(.head_branch)\t\(.name)\t\(.head_sha)"' \
           | sort -t$'\t' -k2,2)
fi
if [ -z "$runs" ]; then
  echo "no queued runs in $repo"
  exit 0
fi
echo "queued in $repo: $(printf '%s\n' "$runs" | grep -c . || true)"

declare -A newest=()
while IFS=$'\t' read -r id created event branch name sha; do
  if [ -z "$id" ]; then continue; fi
  newest["$name"$'\t'"$branch"]="$id"
done <<< "$runs"

while IFS=$'\t' read -r id created event branch name sha; do
  if [ -z "$id" ]; then continue; fi
  case "$event" in schedule) continue ;; esac

  # 0) Starvation ceiling, checked before the newest-skip so a *lone* run that has
  #    been queued for hours still gets freed. This is the deliberate exception to
  #    "always keep the newest": the run can never start, and its commit can be
  #    re-run or superseded by the next push.
  case "$event" in
    pull_request|pull_request_target) ttl=$pr_ttl ;;
    *) ttl=$push_ttl ;;
  esac
  a=$(age_min "$created")
  if [ "$a" -ge "$ttl" ]; then
    cancel "$id" "queued ${a}m >= ${ttl}m ceiling"
    continue
  fi

  key="$name"$'\t'"$branch"
  if [ "${newest[$key]:-}" = "$id" ]; then
    echo "run $id ($name, $branch, $event): keeping — newest for this workflow/ref, ${a}m old"
    continue
  fi

  # 1) Deleted/merged head branch — unstartable zombie.
  if ! branch_exists "$branch"; then
    cancel "$id" "head branch gone"
    continue
  fi

  # 2) Superseded. Only ref-push events: a pull_request run is not superseded
  #    merely because another run on the same branch queued.
  case "$event" in
    push|workflow_dispatch)
      cancel "$id" "superseded by newer run of '$name' on $branch"
      continue
      ;;
  esac

  echo "run $id ($name, $branch, $event): keeping — ${a}m old, under ${ttl}m ceiling"
done <<< "$runs"