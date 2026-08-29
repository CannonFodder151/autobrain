# n8n bridge — `autobrain-deploy-trigger`

Wires a new AutoBrain version deploy to the two release-engineer agent issues,
per **AUT-1905** / **AUT-1911**. Git only emits a signal; n8n does the
agent-triggering. This webhook is called by
`.github/workflows/deploy-instances.yml` (the `notify` job, on image-publish
success).

## Webhook

`POST https://n8n.nathanmartina.com/webhook/autobrain-deploy-trigger`

### Request body (from deploy-instances.yml)

```json
{ "event": "image-published", "version": "1.2.3", "repo": "CannonFodder151/autobrain", "run_id": "1234567890" }
```

## Credential (one-time setup)

The HTTP Request node below needs a Paperclip service credential. Create one of:

- **n8n credential** — add a `Header Auth` credential named `paperclip-deploy`
  with header `Authorization: Bearer <paperclip_api_key>`, **or**
- **GitHub secret** `PAPERCLIP_DEPLOY_TOKEN` — and inject it into n8n at deploy
  time.

The PAT must be able to create issues in the `41d8aeaf` company.

## Workflow (drag nodes)

1. **Webhook** node — `POST /autobrain-deploy-trigger`, response mode
   `onReceived`, returns `{ "ok": true }` (HTTP 200) immediately.
2. **Idempotency check** — before creating issues, call Paperclip
   `GET /api/companies/41d8aeaf-0e55-4127-b037-7a6d740be3b6/issues?labels=deploy:{version}`.
   If a child of `AUT-1905` with label `deploy:{version}` already exists, stop
   (return `{ "ok": true, "skipped": "already-triggered" }`). This makes re-runs
   of the same version a no-op.
3. **Create AUT-1907** — `POST /api/issues` with body:
   ```json
   {
     "parentId": "cdf4f384-29ad-4584-9bf2-4ddc461f6a12",
     "goalId": "4fc32f2e-2489-4333-aa9c-f04aafede71d",
     "title": "Deploy v{version}: update + publish mobile app",
     "description": "Image v{version} published. Mirror frontend, bump pubspec, compile-guard, tag, publish. (Template: AUT-1907.)",
     "assigneeAgentId": "1163f29d-47c5-4903-a0b8-14cd19cb51d7",
     "priority": "medium",
     "labels": ["deploy:{version}"]
   }
   ```
4. **Create AUT-1908** — same `POST`, different title/assignee:
   ```json
   {
     "parentId": "cdf4f384-29ad-4584-9bf2-4ddc461f6a12",
     "goalId": "4fc32f2e-2489-4333-aa9c-f04aafede71d",
     "title": "Deploy v{version}: roll out Demo→test→Default→test→Hosted→test",
     "description": "Image v{version} published. Run upgrade path with per-tier health gating (scripts/upgrade-instances.sh). (Template: AUT-1908.)",
     "assigneeAgentId": "2d3d6e7b-ec81-45c2-8c1e-95456d55bb6e",
     "priority": "medium",
     "labels": ["deploy:{version}"]
   }
   ```
5. **Error handling** — on any node failure, POST to
   `webhook/discord-report` channel `incidents` so the Deployment Lead is paged.

The two issues auto-wake the Mobile Release Engineer and Deployment Engineer
agents. When each finishes it closes its issue; when both are closed, the
`issue_children_completed` continuation on **AUT-1905** auto-closes the parent.

## Verify

Push a test image (or run `notify` manually via `workflow_dispatch` on a tag),
then confirm in Paperclip that exactly one fresh `AUT-1907` + `AUT-1908` pair
appears for that version and that both agents were assigned.
