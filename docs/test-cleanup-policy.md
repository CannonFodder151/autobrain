# Test Cleanup Policy

Whenever an agent creates resources to test a feature, it MUST remove them when
testing is done. Leaving test data, test accounts, or test containers behind
pollutes environments, breaks other people's tests, and costs money.

## Scope

Applies to every environment: local dev, the Paperclip dev box, and
AutoBrain-Hosted (152.69.188.133). Applies to anything created for the test,
including:

- **Accounts** — users created via the app signup/registration flow (frontend
  web + mobile, backend auth endpoints), plus demo/seeded logins.
- **Data** — rows written to Postgres (test cars, trips, diagnostics, entries),
  objects in MinIO/S3 buckets, and files on disk.
- **Containers** — docker compose services, ad-hoc `docker run` containers,
  images built for testing, and any volumes/networks they created.
- **Credentials** — API keys or tokens minted for the test must be revoked.

## Procedure

1. Before you start testing, note every resource you create in a comment on the
   working issue (accounts, data, containers) — this is your cleanup checklist.
2. After the test, work the checklist in reverse:
   - Delete the test account(s) via the app/API, not just the DB row, so
     dependent records are removed too.
   - Delete test data rows and MinIO objects (or drop the test database /
     bucket if the test created one).
   - Remove containers:
     - `docker compose down --rmi local -v` for compose stacks,
     - `docker rm` for ad-hoc containers,
     - `docker image prune -f` (or remove the specific images you built),
     - `docker network prune -f` / `docker volume prune -f` for leftovers.
   - Revoke any keys/tokens the test minted.
3. Confirm cleanup in a comment on the working issue: what was removed and how
   (commands used, exit status). If anything could not be removed, say exactly
   what and who owns the follow-up — do not close the issue silently.

## Enforcement

- Closing a test/feature issue is not valid if the issue's test created
  resources that remain unremoved — cleanup is part of the task.
- The CTO reviews merged PRs and test evidence for cleanup; leftover test
  accounts, data, or containers are a review failure.
