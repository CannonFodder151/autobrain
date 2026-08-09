# Planable Integration

[Planable](https://www.planable.io) is the social content planning / approval
workflow used by the marketing team. It connects social pages (Facebook,
Instagram, LinkedIn, X, TikTok, Threads, YouTube, Google Business Profile,
Pinterest) into one calendar with draft → review → approval → schedule →
publish, plus an inbox and analytics.

AutoBrain agents talk to Planable over **MCP** (Model Context Protocol) so
marketing automation is driven from the agent runtime instead of manual
copy-paste. The AI only ever creates drafts and moves posts through the
existing Planable approval workflow — it never publishes directly.

## Planable MCP server

- Endpoint: `https://mcp.planable.io/mcp`
- Transport: HTTP + Streamable-HTTP (OpenAI/Anthropic MCP compatible)
- Auth: bearer token — a Planable API token scoped to the account the agents
  act on behalf of. `Authorization: Bearer <planable_api_token>`
- Reference: [Planable MCP announcement](https://planable.io/blog/planable-mcp/),
  [connect guide](https://help.planable.io/hc/en-us/articles/27538577098780-How-to-connect-Planable-MCP-to-your-AI-tools)

### What agents can do

| Area | Actions |
|------|---------|
| Account structure | list companies / workspaces, connected social pages, members + roles, labels, post counts |
| Read content | list posts (filter by status, approval state, date), read full post content, team notes, client comments |
| Create / edit | create draft posts (single page or synced group post), update text / schedule / labels / media, add first comment, attach media via URL, upload to media library, create labels |
| Approvals | approve (incl. multi-level), reject / disapprove, leave notes / public comments |
| Media library | list media, get item details, upload from URL |
| Analytics | per-page / per-post / aggregated metrics; triggers a metrics refresh first (Analytics add-on required) |

### Limits

- Inherits the account's Planable permissions — it can approve only what the
  account can approve.
- Creates drafts, never published posts.
- Cannot change account settings, billing, or workspace configuration.
- Analytics calls fail when the workspace has no Analytics add-on.

## Wiring in the agent runtime

The Paperclip agents run under the opencode runtime on the dev box. The
Planable MCP server is registered in the global opencode config
(`~/.config/opencode/opencode.jsonc`) as a remote MCP server, token-gated:

```jsonc
"mcp": {
  "planable": {
    "type": "remote",
    "url": "https://mcp.planable.io/mcp",
    "headers": {
      "Authorization": "Bearer {env:planable_api_token}"
    },
    "enabled": false
  }
}
```

The server stays `enabled: false` until the `planable_api_token` Paperclip
secret exists (env delivery). Flip it to `true` once the token is live.

### Secret

- Paperclip secret key: `planable_api_token` (delivery: `env`)
- The token must belong to a Planable account that is a member of the AutoBrain
  workspace(s) the agents manage.

## Activation checklist

1. [ ] Nathan (or a Planable admin) creates the AutoBrain workspace(s) in
      Planable and connects the social pages (including the AutoBrain
      Facebook page — see `AUT-127`).
2. [ ] Generate a Planable API token and propose it as Paperclip secret
      `planable_api_token` (never paste it into chats/issues).
3. [ ] Flip `planable` MCP `enabled: true` in the opencode config.
4. [ ] Smoke test: list workspaces, list posts, create one draft on the
      AutoBrain page, approve it through the normal flow.
5. [ ] Publish one scheduled post and confirm it lands.

## Relationship to the existing social pipeline

- `n8n WF-4 Social Posting Queue` + `Social Queue` Outline doc remain the
  publishing queue; Planable adds calendar planning, approvals, and analytics
  on top.
- Facebook posting/messaging work in `AUT-127` connects the AutoBrain page
  directly via the Meta Graph API. Planable is complementary — for planning
  and approvals — not a replacement for the Messenger webhook path.
