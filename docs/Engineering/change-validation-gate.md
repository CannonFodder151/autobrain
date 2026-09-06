# Change Validation Gate

**Owner:** CEO (policy) / CTO (enforcement). **Last reviewed:** 2026-08-11 (AUT-381).

Mandatory two-gate process for every change to the AutoBrain stack (backend, AI
gateway, frontend, infra, deployment config). Mirrors the Paperclip issue
workflow; the gates are enforced on the issue, not in CI (there is no PR-level
CI today — see `docs/test-strategy.md`).

## The two gates

### Gate 1 — Security before build

Every change MUST get Security sign-off BEFORE implementation is allowed to
start.

- Owner of the gate: **Security Officer** (issues AUT-203, AUT-206, AUT-172 are
  the standing pattern).
- Scope: ALL changes, including bug fixes, refactors and docs. Triage is fast:
  a change that does not touch auth, data, inputs, egress or secrets is an
  auto-pass noted on the issue.
- Enforcement: the engineering issue is created with a `security-review`
  dependency or is blocked by an explicit Security issue. No implementation
  runs until the Security Officer posts sign-off (or auto-pass) on the issue.
- Security-critical changes (auth, payments, data access, secrets, network)
  get a full review + pen-test where warranted, not an auto-pass.

### Gate 2 — QA immediately after push

The QA & User Testing agent MUST run a test pass immediately after a change is
pushed/merged, and before it is promoted to the next tier.

- Owner of the gate: **QA & User Testing** (Senior QA Reviewer backstops).
- Timing: start within the same day of the merge/push; do not wait for a
  release to accumulate.
- Scope: automated suites (`pytest` backend + ai in the stack) plus the manual
  coverage areas against the dev box, logged to `docs/qa-run-logs.md`.
- Promotion (Demo → Default → Hosted) only proceeds after the post-push pass is
  green; release-blocking bugs must be fixed and re-verified first.

## Definition of done (both gates)

A change is `done` only when ALL hold:

1. Security Officer sign-off (or recorded auto-pass) is on the issue BEFORE build.
2. Change is pushed/merged.
3. QA post-push test pass is recorded in `docs/qa-run-logs.md`.
4. Promotion order Demo → Default → Hosted was followed (AUT-107) where applicable.

## Enforcement & escalation

- CTO owns enforcement: engineering issues are not started without Gate 1 and
  not closed without Gate 2.
- CEO audits weekly: any issue shipped without both gates is a process
  violation and gets flagged to the board.
- 9Router failure never skips a gate — sign-off and test-pass are human/agent
  checkpoints, not AI calls.

### Security-relevant changes land via PR only

Security-relevant changes (auth, data access, secrets, network, dependency
pins, config defaults) MUST be submitted as pull requests, reviewed, and
merged through the PR. Direct pushes to `main` are not permitted for these
changes — Gate 1 sign-off does not waive the PR path.

- Owner: CTO.
- Review bar: the Security Officer's Gate 1 sign-off is a precondition; the
  merging reviewer confirms the pushed diff matches the signed-off code.
- Long-term: add PR-level CI checks (SAST + lint) so the gate is machine
  enforced too (tracked on the engineering backlog).
- Known history: `5ee86d3` (AUT-200) and `9ca989f` (AUT-199) predate this
  rule; both were retroactively signed off (AUT-248 verdict) and covered by
  Gate 2 QA. They are not a precedent for future commits.

## Related

- `docs/test-strategy.md` — environments, coverage areas, sign-off bar.
- `docs/security.md` — security review scope and runbooks.
- `CONTRIBUTING.md` — branch/PR/commit rules for contributors.
