# Social Image Generation & Publishing (LinkedIn + Facebook)

Status: **proven working** (AUT-163). Target platforms: **LinkedIn and Facebook only**.

## How images are generated

9Router currently exposes **no image-output model** (verified against `/v1/models`:
every model has `imageOutput: false`). AutoBrain therefore generates social
images with a **deterministic-first** approach, matching the company rule of
"deterministic paths first, AI fallback":

1. **Primary — branded card generator** (`ai/app/modules/social_image.py`):
   renders an on-brand AutoBrain card (headline, hook, CTA on the charcoal/teal
   palette) with Pillow. No network, no cost, never fails. Output: PNG (default
   1200×630, fits both LinkedIn and Facebook feed posts).
2. **AI fallback** — when the caller supplies a `prompt` (photoreal/illustrative
   art direction), the module tries the free Pollinations text-to-image endpoint;
   if that fails it falls back to the deterministic card. `model` in the response
   reports which path ran (`rule-based-card` vs `pollinations-ai`).

Exposed as the `social-image` module on the AI gateway: `POST /v1/social-image`
with `{"title", "hook", "cta", "prompt"?, "width"?, "height"?}` → base64 PNG +
metadata.

## End-to-end publishing flow (proven)

```
1. Social Media Manager drafts post copy            → Outline "Social Queue" doc
2. Generate image                                   → AI gateway /v1/social-image
3. Host PNG at a public URL                         → GitHub raw / MinIO public
4. Post to LinkedIn + Facebook via Buffer MCP       → Buffer channels below
```

Buffer is the publish layer. Verified live channels (org **My Organization**):

| Channel  | ID                              | Notes                                |
|----------|---------------------------------|--------------------------------------|
| LinkedIn | `6a78595bb2d9d57743445c3c`      | page autobrainservice ("AutoBrain")  |
| Facebook | `6a7859acb2d9d57743445d31`      | page AutoBrain                       |

Publish rules learned in AUT-163:

- LinkedIn and Facebook channels require `schedulingType: automatic`
  (`notification` is rejected: `Notification scheduling is not supported`).
- Facebook posts require `metadata.facebook.type` (`post` | `story` | `reel`).
- Use `saveToDraft: true` until Nathan approves a post — never auto-publish
  without sign-off. Default `mode: addToQueue` (draft = queue slot + approval).
- Image asset goes in `assets[].image.url`; set `altText` in
  `image.metadata.altText` for accessibility.

Proof (2026-08-09): a generated card (`social/assets/sample-linkedin.png`,
hosted on GitHub raw) was posted to **both** channels as drafts:
LinkedIn `6a78829b523554e5ff62319f`, Facebook `6a7882a5634795f2bafb5b50`.

## n8n automation note

n8n has **no Buffer credential type/node** installed, so the Social Queue
workflow (WF-4) cannot post to Buffer directly yet. The reliable automation path
today is agent-driven: the Social Media Manager reads the queue and posts via the
Buffer MCP tools (create_post), which the drafts above prove works. If a Buffer
n8n node/credential is added later, WF-4 can swap its Discord node for Buffer.

## Next steps

- [ ] Nathan approves the two proof drafts in Buffer.
- [ ] Social Media Manager fills the Social Queue with LinkedIn + Facebook posts
      using the generated cards (Content Batch 1 art direction → prompts).
- [ ] Move hosted image assets from GitHub raw to MinIO public bucket
      (`MINIO_PUBLIC_ENDPOINT`/`APP_BASE_URL`) so cards are served from the app
      domain. `ponytail:` GitHub raw was used for the proof because it needed no
      credentials; swap when a hosted bucket is configured.
