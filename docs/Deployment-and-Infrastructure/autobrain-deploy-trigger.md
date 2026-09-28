# n8n bridge — `autobrain-deploy-trigger`

Wires a new AutoBrain hosted image deploy to the Mobile Release Engineer and
Deployment Lead agent issues. Git only emits a signal; n8n does the
agent-triggering. This webhook is called by
`.github/workflows/deploy-instances.yml` (the `notify` job, on image-publish
success).

**OVERRIDE ACTIVE (AUT-2409):** The AUT-107 three-tier promotion chain (Demo → Default → Hosted) is **PAUSED**. The bridge now only triggers the Mobile Release Engineer and the Deployment Lead for **hosted-only** deploys in the nightly 03:00–04:00 AEST window.

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
   If a child of the parent deployment issue with label `deploy:{version}` already exists, stop
   (return `{ "ok": true, "skipped": "already-triggered" }`). This makes re-runs
   of the same version a no-op.
3. **Create Mobile Release Engineer issue** — `POST /api/issues` with body:
   ```json
   {
     "parentId": "<deployment-parent-issue-uuid>",
     "goalId": "<goal-uuid>",
     "title": "Deploy v{version}: update + publish mobile app",
     "description": "Image v{version} published. Mirror frontend, bump pubspec, compile-guard, tag, publish. (Template: AUT-1907.)",
     "assigneeAgentId": "1163f29d-47c5-4903-a0b8-14cd19cb51d7",
     "priority": "medium",
     "labels": ["deploy:{version}"]
   }
   ```
4. **Create Deployment Lead issue** — same `POST`, different title/assignee:
   ```json
   {
     "parentId": "<deployment-parent-issue-uuid>",
     "goalId": "<goal-uuid>",
     "title": "Deploy v{version}: run hosted upgrade path (EP5, 03:00–04:00 AEST)",
     "description": "Image v{version} published. Run upgrade-instances.sh against Portainer EP5 with pullImage:true. Health-gate on hosted.autobrainservice.app/health. Create post-deploy QA child issue. (Template: AUT-1908.)",
     "assigneeAgentId": "285b6a03-80f7-4a36-ba06-d5831371afce",
     "priority": "medium",
     "labels": ["deploy:{version}"]
   }
   ```
5. **Error handling** — on any node failure, POST to
   `webhook/discord-report` channel `incidents` so the Deployment Lead is paged.

The two issues auto-wake the Mobile Release Engineer and Deployment Lead
agents. When each finishes it closes its issue; when both are closed, the
`issue_children_completed` continuation on the parent deployment issue auto-closes the parent.

## Verify

Push a test image (or run `notify` manually via `workflow_dispatch` on a tag),
then confirm in Paperclip that exactly one fresh Mobile Release Engineer +
Deployment Lead pair appears for that version and that both agents were assigned.

---

**Related docs:** [`deployment-guide.md`](./deployment-guide.md) | [`ci-cd.md`](./ci-cd.md) | [`deploy-instances.yml`](../../.github/workflows/deploy-instances.yml)

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.