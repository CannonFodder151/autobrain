#!/usr/bin/env python3
"""
Discord #marketing approval watcher.

Polls GET /channels/{id}/messages every run and treats text replies from the
human CMO (Nathan) as decisions, in addition to emoji reactions.

  approve: approve | approved | yes | ship it
  reject:  reject | no | block

Decisions are resolved to a Paperclip issue by:
  1. an AUT-XXXX reference in the message's own embeds, else
  2. the most recent preceding bot message that embeds an AUT-XXXX reference
     (this is the case Nathan actually uses — a bare "Approve all" reply).

Approval marks the issue done; rejection marks it blocked with an unblock owner.
Reactions (✅/❌) on bot approval embeds are still honoured.

Run once:   python3 scripts/approval_watcher.py
Self-check: APPROVAL_WATCHER_TEST=1 python3 scripts/approval_watcher.py
"""

import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("approval-watcher")

DISCORD_API = "https://discord.com/api/v10"
NATHAN_USER_ID = "132444441024790529"
AUT_RE = re.compile(r"\bAUT-(\d+)\b")
APPROVE_RE = re.compile(r"\b(approve|approved|yes|ship it)\b", re.IGNORECASE)
REJECT_RE = re.compile(r"\b(reject|no|block)\b", re.IGNORECASE)


@dataclass
class Config:
    bot_token: str
    channel_id: str
    paperclip_url: str
    paperclip_key: str
    company_id: str
    nathan_user_id: str = NATHAN_USER_ID
    state_file: str = os.environ.get(
        "APPROVAL_WATCHER_STATE", "/tmp/approval_watcher_state.json"
    )

    @classmethod
    def from_env(cls) -> "Config":
        missing = [
            k
            for k in (
                "DISCORD_BOT_TOKEN",
                "DISCORD_CHANNEL_MARKETING",
                "PAPERCLIP_API_URL",
                "PAPERCLIP_API_KEY",
                "PAPERCLIP_COMPANY_ID",
            )
            if not os.environ.get(k)
        ]
        if missing:
            raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
        return cls(
            bot_token=os.environ["DISCORD_BOT_TOKEN"],
            channel_id=os.environ["DISCORD_CHANNEL_MARKETING"],
            paperclip_url=os.environ["PAPERCLIP_API_URL"].rstrip("/"),
            paperclip_key=os.environ["PAPERCLIP_API_KEY"],
            company_id=os.environ["PAPERCLIP_COMPANY_ID"],
            nathan_user_id=os.environ.get("NATHAN_DISCORD_ID", NATHAN_USER_ID),
        )


def _discord_headers(cfg: Config) -> dict:
    return {"Authorization": f"Bot {cfg.bot_token}"}


def fetch_messages(cfg: Config, after: Optional[str] = None, limit: int = 100) -> list:
    params = {"limit": limit}
    if after:
        params["after"] = after
    r = requests.get(
        f"{DISCORD_API}/channels/{cfg.channel_id}/messages",
        headers=_discord_headers(cfg),
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def detect_decision(text: str) -> Optional[str]:
    if APPROVE_RE.search(text):
        return "approve"
    if REJECT_RE.search(text):
        return "reject"
    return None


def find_aut_ref(*texts: str) -> Optional[str]:
    for text in texts:
        m = AUT_RE.search(text or "")
        if m:
            return f"AUT-{m.group(1)}"
    return None


def message_aut_ref(msg: dict) -> Optional[str]:
    """AUT-XXXX referenced by a message's own content or embeds."""
    if AUT_RE.search(msg.get("content") or ""):
        return find_aut_ref(msg["content"])
    for embed in msg.get("embeds", []):
        parts = [embed.get("title", ""), embed.get("description", "")]
        parts += [f.get("value", "") for f in embed.get("fields", [])]
        ref = find_aut_ref(*parts)
        if ref:
            return ref
    return None


def nathan_reacted(cfg: Config, msg_id: str, emoji: str) -> bool:
    url = (
        f"{DISCORD_API}/channels/{cfg.channel_id}/messages/"
        f"{msg_id}/reactions/{quote(emoji)}"
    )
    r = requests.get(
        url, headers=_discord_headers(cfg), params={"limit": 100}, timeout=15
    )
    if r.status_code == 404:
        return False
    r.raise_for_status()
    return any(u.get("id") == cfg.nathan_user_id for u in r.json())


def resolve_issue_id(cfg: Config, identifier: str) -> Optional[str]:
    """Map AUT-XXXX -> Paperclip issue UUID."""
    r = requests.get(
        f"{cfg.paperclip_url}/api/companies/{cfg.company_id}/issues",
        headers={"Authorization": f"Bearer {cfg.paperclip_key}"},
        params={"q": identifier},
        timeout=20,
    )
    r.raise_for_status()
    for issue in r.json():
        if issue.get("identifier") == identifier:
            return issue["id"]
    return None


def apply_decision(cfg: Config, identifier: str, decision: str, source: str) -> bool:
    issue_id = resolve_issue_id(cfg, identifier)
    if not issue_id:
        log.warning("No Paperclip issue found for %s (%s)", identifier, source)
        return False

    if decision == "approve":
        payload = {
            "status": "done",
            "comment": (
                f"Approved by human CMO in Discord #marketing ({source}). "
                "Detected automatically by the approval watcher."
            ),
        }
    else:
        payload = {
            "status": "blocked",
            "comment": (
                f"Rejected by human CMO in Discord #marketing ({source}). "
                "Detected automatically by the approval watcher. "
                "Unblock owner: Nathan — reply in #marketing with the changes needed."
            ),
        }

    r = requests.patch(
        f"{cfg.paperclip_url}/api/issues/{issue_id}",
        headers={
            "Authorization": f"Bearer {cfg.paperclip_key}",
            "Content-Type": "application/json",
            "X-Paperclip-Run-Id": os.environ.get("PAPERCLIP_RUN_ID", "approval-watcher"),
        },
        json=payload,
        timeout=20,
    )
    if r.status_code not in (200, 201):
        log.error("Failed to %s %s: %s %s", decision, identifier, r.status_code, r.text[:400])
        return False
    log.info("Applied %s to %s (from %s)", decision, identifier, source)
    return True


def process_batch(cfg: Config, messages: list) -> int:
    """messages must be oldest-first. Returns count of decisions applied."""
    acted = 0
    last_bot_ref = None

    for msg in messages:
        author = msg.get("author", {})

        if author.get("id") == cfg.nathan_user_id:
            decision = detect_decision(msg.get("content", ""))
            if decision:
                ref = message_aut_ref(msg) or last_bot_ref
                if ref:
                    if apply_decision(cfg, ref, decision, f"message {msg['id']}"):
                        acted += 1
                else:
                    log.warning(
                        "Decision '%s' in %s has no resolvable AUT reference; skipping",
                        msg.get("content", "")[:60],
                        msg["id"],
                    )

        # Track the most recent bot embed message so a bare reply resolves.
        if author.get("username") == "AutoBrain App":
            ref = message_aut_ref(msg)
            if ref:
                last_bot_ref = ref
                for emoji, decision in (("✅", "approve"), ("❌", "reject")):
                    if nathan_reacted(cfg, msg["id"], emoji):
                        if apply_decision(cfg, ref, decision, f"{emoji} reaction on {msg['id']}"):
                            acted += 1

    return acted


def load_state(cfg: Config) -> Optional[str]:
    try:
        with open(cfg.state_file) as fh:
            return json.load(fh).get("last_message_id")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(cfg: Config, message_id: str) -> None:
    os.makedirs(os.path.dirname(cfg.state_file) or ".", exist_ok=True)
    with open(cfg.state_file, "w") as fh:
        json.dump({"last_message_id": message_id}, fh)


def run_once(cfg: Config) -> int:
    last_id = load_state(cfg)
    messages = fetch_messages(cfg, after=last_id)
    if not messages:
        log.info("No new messages since %s", last_id or "beginning of channel")
        return 0

    messages.reverse()  # Discord returns newest-first
    acted = process_batch(cfg, messages)
    save_state(cfg, messages[-1]["id"])
    log.info("Processed %d message(s), applied %d decision(s)", len(messages), acted)
    return acted


def main() -> None:
    cfg = Config.from_env()
    run_once(cfg)


def _self_test() -> None:
    # Decision keywords
    for text in ("Approve all", "approved", "APPROVED", "Yes", "yes please", "Ship it", "SHIP IT"):
        assert detect_decision(text) == "approve", text
    for text in ("Reject", "REJECT THIS", "no", "No thanks", "Block"):
        assert detect_decision(text) == "reject", text
    for text in ("Maybe later", "", "the approval flow"):
        assert detect_decision(text) is None, text

    # AUT reference extraction
    assert find_aut_ref("batch for AUT-4422 ready") == "AUT-4422"
    assert find_aut_ref("no reference here") is None
    assert (
        message_aut_ref({"content": "", "embeds": [{"title": "AUT-4422: Batch", "fields": []}]})
        == "AUT-4422"
    )
    assert (
        message_aut_ref(
            {
                "content": "",
                "embeds": [
                    {"title": "no id", "fields": [{"name": "Issue", "value": "AUT-4507"}]}
                ],
            }
        )
        == "AUT-4507"
    )
    assert message_aut_ref({"content": "approve AUT-4430", "embeds": []}) == "AUT-4430"
    assert message_aut_ref({"content": "Approve all", "embeds": []}) is None

    # Batch: bare "Approve all" resolves via preceding bot embed.
    class _Cfg:
        def __init__(self):
            self.calls = []
            self.nathan_user_id = NATHAN_USER_ID

        def __getattr__(self, item):
            return lambda *a, **k: False

    def fake_apply(cfg_, identifier, decision, source):
        cfg_.calls.append((identifier, decision, source))
        return True

    def fake_reacted(cfg_, msg_id, emoji):
        return emoji == "❌" and msg_id == "m1"

    import approval_watcher as self_module

    orig_apply, orig_reacted = self_module.apply_decision, nathan_reacted
    self_module.apply_decision, self_module.nathan_reacted = fake_apply, fake_reacted
    try:
        cfg = _Cfg()
        n = self_module.process_batch(
            cfg,
            [
                {"id": "m1", "content": "", "author": {"username": "AutoBrain App"},
                 "embeds": [{"title": "AUT-4422: Approval Request", "fields": []}]},
                {"id": "m2", "content": "Approve all", "author": {"id": NATHAN_USER_ID}},
                {"id": "m3", "content": "block that one", "author": {"id": NATHAN_USER_ID}},
            ],
        )
    finally:
        self_module.apply_decision, self_module.nathan_reacted = orig_apply, orig_reacted

    # m1: ❌ reaction on the AUT-4422 bot embed
    # m2: bare "Approve all" with no embed -> resolves via preceding bot message
    # m3: "block that one" -> reject the same issue
    assert n == 3, (n, cfg.calls)
    assert cfg.calls[0] == ("AUT-4422", "reject", "❌ reaction on m1"), cfg.calls
    assert cfg.calls[1] == ("AUT-4422", "approve", "message m2"), cfg.calls
    assert cfg.calls[2] == ("AUT-4422", "reject", "message m3"), cfg.calls

    # A decision with no resolvable reference must be skipped, not crash.
    self_module.apply_decision, self_module.nathan_reacted = fake_apply, fake_reacted
    try:
        cfg2 = _Cfg()
        n2 = self_module.process_batch(
            cfg2,
            [{"id": "x1", "content": "approve", "author": {"id": NATHAN_USER_ID}}],
        )
    finally:
        self_module.apply_decision, self_module.nathan_reacted = orig_apply, orig_reacted
    assert n2 == 0, (n2, cfg2.calls)

    print("Self-test passed")


if __name__ == "__main__":
    if os.environ.get("APPROVAL_WATCHER_TEST") == "1":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        _self_test()
        sys.exit(0)
    main()
