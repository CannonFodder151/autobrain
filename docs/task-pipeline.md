# Task Pipeline

How AutoBrain agents create, verify, and link work items through Paperclip. This is the
contract between the run-time harness and the control plane: every sub-task and
follow-up **must** go through the API, **must** be verified by HTTP 201 + identifier,
and only **then** may the parent be commented.

The verify-then-comment rule exists because the liveness checker marks any parent
that surfaces follow-ups without a verified child as `needs_followup` and blocks
the run.

## Core rule

> **Create the child via `POST /api/companies/{companyId}/issues`, verify the response
> is HTTP 201 with a real identifier (e.g. `AUT-1977`), then add a parent comment
> referencing that identifier. Never claim a child exists based on a comment,
> invented id, or assumption.**

The parent comment must include the **real** identifier returned by the API, not
a guess like `AUT-1964-1`. If the API call fails, retry once; if it still fails,
comment the exact error on the parent and flag the failure in Discord `#ops`.

## Canonical curl: create a sub-task or follow-up

```bash
curl -s -X POST "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Short imperative title (<=90 chars)",
    "description": "1-3 sentence description + acceptance criteria. Link parent: see AUT-XXXX.",
    "status": "todo",
    "priority": "high",
    "parentId": "PARENT_ISSUE_UUID",
    "goalId": "GOAL_UUID_IF_KNOWN",
    "assigneeAgentId": "ASSIGNEE_AGENT_UUID"
  }'
```

Field reference:

| Field | Required | Notes |
|-------|----------|-------|
| `title` | yes | Imperative, <= 90 chars |
| `description` | yes | Acceptance criteria; reference parent `AUT-XXXX` |
| `status` | yes | `todo` (wakes the assignee). **Never** `blocked` |
| `priority` | yes | `high` for outage sub-tasks; otherwise normal |
| `parentId` | yes | The current issue's UUID (`PAPERCLIP_TASK_ID` or from issue JSON) |
| `goalId` | when known | Goal UUID — keeps the child in the goal hierarchy |
| `assigneeAgentId` | when routing | UUID of the agent who will execute the child |

## Verify-then-comment flow

```bash
# 1. Create
RESP=$(curl -s -w "\n%{http_code}" -X POST \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d @child.json)

# 2. Verify: HTTP 201 + identifier (e.g. AUT-1977)
BODY=$(echo "$RESP" | head -n -1)
CODE=$(echo "$RESP" | tail -n 1)
if [ "$CODE" != "201" ]; then
  echo "create failed: $BODY"; exit 1
fi

CHILD_ID=$(echo "$BODY" | python3 -c "import json,sys; print(json.load(sys.stdin)['identifier'])")

# 3. Cross-check the child is visible from the parent
curl -s "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues?parentId=$PARENT_UUID" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" | grep -q "$CHILD_ID" \
  || { echo "child not linked to parent"; exit 1; }

# 4. Only now comment on the parent with the real id
curl -s -X POST "$PAPERCLIP_API_URL/api/issues/$PARENT_UUID/comments" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"body\":\"Created child $CHILD_ID — <title>\"}"
```

## Bad example (will fail liveness)

```bash
# ❌ Do NOT do this. No API. No identifier. Parent comment invents a child.
curl -s -X POST "$PAPERCLIP_API_URL/api/issues/$PARENT_UUID/comments" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -d '{"body":"Created sub-task AUT-1964-1 (will fix later)"}'
```

Why it fails:

- No `POST /api/companies/.../issues` call → no real child created.
- Identifier `AUT-1964-1` is invented, not returned by the API.
- Parent surfaces a follow-up but the liveness checker finds zero children →
  run is marked `needs_followup` and blocked.

## Good example (passes liveness)

```bash
# ✅ Create, verify, then comment.
curl -s -w "\n%{http_code}" -X POST \
  "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Fix alembic migration chain on main",
    "description": "Resolves duplicate revision from AUT-918; see AUT-996.",
    "status": "todo",
    "priority": "high",
    "parentId": "82ec51bf-84c4-4768-8006-bd93830aebc8",
    "goalId": "4fc32f2e-2489-4333-aa9c-f04aafede71d",
    "assigneeAgentId": "285b6a03-80f7-4a36-ba06-d5831371afce"
  }'
# -> 201 { "identifier": "AUT-1087", ... }

curl -s -X POST "$PAPERCLIP_API_URL/api/issues/82ec51bf-.../comments" \
  -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
  -d '{"body":"Created child AUT-1087 — Fix alembic migration chain on main"}'
```

Why it passes:

- API call returned 201 with a real identifier (`AUT-1087`).
- Child is queryable via `GET .../issues?parentId=...` and visible to the checker.
- Parent comment cites the **real** id from the API response.

## Anti-hallucination checklist

Run these before commenting on the parent:

- [ ] Called `POST /api/companies/{companyId}/issues`?
- [ ] Saw HTTP 201?
- [ ] Used the **returned** `identifier` in the parent comment (no invented suffix)?
- [ ] Verified the child appears via `GET /api/companies/{companyId}/issues?parentId={parentId}`?

If any answer is no: retry once. If it still fails, comment the exact error on the
parent and flag in Discord `#ops` — do **not** comment a fabricated identifier.

## Other rules

- `status` MUST be `todo` (wakes the assignee). `blocked` is only for issues with a
  real first-class unblock owner; do not use it as a synonym for "parked".
- `priority` `high` for outage / production-down sub-tasks. Use the standard ladder
  (`low` / `medium` / `high` / `critical`) otherwise.
- Always set `parentId` on children of a current issue; the parent UUID is
  `PAPERCLIP_TASK_ID` or available in the issue JSON.
- Set `goalId` when known — keeps the child attached to the company goal.
- For `resume: true` continuations on closed issues, include the structured marker in
  the comment payload (see Heartbeat Protocol).
- When the board/user must choose between tasks, use issue-thread interactions
  (`suggest_tasks`, `ask_user_questions`, `request_confirmation`) — not comments.

## Batch decomposition

If a parent lists multiple discrete items (e.g. "fix three migrations"), create one
child per item **before** starting work. Verify each child, then comment on the
parent with the list of verified identifiers.

```bash
for ITEM in "Fix migration A" "Fix migration B" "Fix migration C"; do
  curl -s -X POST "$PAPERCLIP_API_URL/api/companies/$PAPERCLIP_COMPANY_ID/issues" \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"title\":\"$ITEM\",
      \"description\":\"Child of AUT-XXXX\",
      \"status\":\"todo\",
      \"priority\":\"high\",
      \"parentId\":\"$PARENT_UUID\"
    }" | python3 -c "import json,sys; print(json.load(sys.stdin)['identifier'])"
done
```

## Reference: where else this matters

- `AGENTS.md` for the CTO and other roles contains the same rule in the agent
  instructions (search for "MANDATORY API PATTERN").
- `docs/heartbeat-protocol.md` (Paperclip) covers the wider heartbeat lifecycle.
- Run liveness states — `needs_followup` is the failure mode this rule prevents.

## Pre-exit guardrail (AUT-1992)

A run that surfaces follow-ups but never POSTs a child is a defect class of its own
(marked `needs_followup`, blocked, repeated). The mechanical check lives in
`scripts/check-followup-guardrail.sh`. Run it from the last step of every heartbeat
**before** you `PATCH` the issue to `done`:

```bash
bash scripts/check-followup-guardrail.sh "$PAPERCLIP_RUN_SCRATCH_DIR"
# exit 0 = pass
# exit 1 = follow-up signals present, no children -> create them, re-run, then close
# exit 2 = skipped (no transcript available) -> safe to proceed
```

The script scans the run scratch dir for `.txt`/`.md`/`.log` artefacts, counts
follow-up signal words (`todo`, `follow-up`, `next step`, `create child/issue`,
`new aut/issue`, `assignee must/should/will`), and if it finds ≥ 2 signals it calls
`GET /api/companies/{companyId}/issues?parentId={PAPERCLIP_TASK_ID}` to verify at
least one child exists. If not, it exits 1 with the exact `POST` body you should
use to fix the gap.

This is belt-and-braces over the manual checklist: it runs even when the agent
forgets the rule. Skip-on-empty-transcript (`exit 2`) keeps it from blocking
agents whose harness does not surface a transcript dir.