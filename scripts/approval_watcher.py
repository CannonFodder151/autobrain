#!/usr/bin/env python3
"""AUT-4535 / AUT-5450: detect #marketing approval decisions, including text.

Approval monitoring only watched emoji reactions, so Nathan's text replies
("Approved", "ship it") were never seen: AUT-3989 and AUT-4507 both sat
unanswered in #marketing. This polls channel messages via
GET /channels/{id}/messages and reports text decisions as well as reactions.

One watcher covers current and future approval tasks because the target is
resolved per message (own text, the message it replies to, else the nearest
preceding bot message) instead of from a pre-registered list.

Env:
  DISCORD_BOT_TOKEN           bot token (Paperclip secret `Discord Bot Token`)
  DISCORD_CHANNEL_MARKETING   channel id, default 1537312915328339998
  NATHAN_DISCORD_ID           decision author, default 132444441024790529
  PAPERCLIP_API_URL, PAPERCLIP_API_KEY, PAPERCLIP_COMPANY_ID  required by --apply
  APPROVAL_WATCHER_STATE      dedup cursor file, default
                              ~/.cache/autobrain/approval-watcher.json

Run:
  python3 scripts/approval_watcher.py             # detect only, JSON out
  python3 scripts/approval_watcher.py --apply     # also record on the issue
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_MARKETING_CHANNEL = "1537312915328339998"
DEFAULT_NATHAN_ID = "132444441024790529"
DEFAULT_STATE = "~/.cache/autobrain/approval-watcher.json"
# Datacenter egress gets Cloudflare error 1010 without a Discord-style UA
# (AUT-4844), so every call sends one.
USER_AGENT = "AutoBrainApprovalWatcher/1.0 (discord.com)"
PAGE = 100

APPROVE_REACTIONS = frozenset({"✅", "👍", "🟢", "☑️", "✔️"})
REJECT_REACTIONS = frozenset({"❌", "👎", "🔴", "⛔", "🛑"})

AUT_RE = re.compile(r"\bAUT-(\d+)\b", re.I)
APPROVE_PHRASES = ("approve", "ship it", "lgtm", "go ahead", "green light")
REJECT_PHRASES = (
    "reject",
    "block",
    "hold off",
    "not yet",
    "do not ship",
    "cancel",
    "no go",
)
NEGATION_RE = re.compile(
    r"\b(?:not|never|no|don't|do not|doesn't|isn't|aren't|can't|won't|n't)\W*$", re.I
)
SHORT_APPROVE_RE = re.compile(r"(?:yes|yeah|yep|yup|ya|sure|ok|okay|approved?)\W*$", re.I)
SHORT_REJECT_RE = re.compile(r"(?:no|nope|nah|rejected?|blocked?)\W*$", re.I)


@dataclass(frozen=True)
class Decision:
    issue: str
    verdict: str
    source: str
    message_id: str
    author_id: str
    content: str
    created_at: str

    @property
    def key(self) -> str:
        return f"{self.issue}:{self.verdict}:{self.source}:{self.message_id}"


def _negated(text: str, start: int) -> bool:
    return bool(NEGATION_RE.search(text[max(0, start - 24) : start]))


def _hits(text: str, phrases) -> bool:
    """True when any phrase appears without a negation right before it."""
    return any(
        not _negated(text, m.start())
        for phrase in phrases
        for m in re.finditer(re.escape(phrase), text)
    )


def classify_text(content: str):
    """Map message text to 'approve'/'reject', or None when it is not a decision.

    A negated approval ("not approved", "I don't approve") is a rejection, and
    a message carrying both an approval and a rejection phrase is left undecided
    rather than guessed at.
    """
    text = content.strip().lower()
    if not text:
        return None
    if SHORT_APPROVE_RE.fullmatch(text):
        return "approve"
    if SHORT_REJECT_RE.fullmatch(text):
        return "reject"
    approve = _hits(text, APPROVE_PHRASES)
    reject = _hits(text, REJECT_PHRASES)
    if approve and not reject:
        return "approve"
    if reject and not approve:
        return "reject"
    if approve or reject:
        return None
    return "reject" if any(_negated(text, m.start()) for p in APPROVE_PHRASES
                           for m in re.finditer(re.escape(p), text)) else None


def message_text(message: dict) -> str:
    parts = [message.get("content") or ""]
    for embed in message.get("embeds") or []:
        parts += [
            embed.get("title") or "",
            embed.get("description") or "",
            (embed.get("footer") or {}).get("text") or "",
        ]
    return "\n".join(p for p in parts if p)


def issue_in(message: dict):
    match = AUT_RE.search(message_text(message))
    return f"AUT-{match.group(1)}" if match else None


def resolve_target(message: dict, by_id: dict, last_issue):
    match = AUT_RE.search(message.get("content") or "")
    if match:
        return f"AUT-{match.group(1)}"
    reference = message.get("message_reference") or {}
    parent = by_id.get(reference.get("message_id"))
    if parent and issue_in(parent):
        return issue_in(parent)
    return last_issue


def scan(messages: list, nathan_id: str) -> list:
    """Find approval decisions in chronologically ordered channel messages."""
    by_id = {m["id"]: m for m in messages}
    decisions = []
    last_issue = None
    for message in messages:
        named = issue_in(message)
        if named:
            last_issue = named
        verdict = classify_text(message_text(message))
        if verdict and str((message.get("author") or {}).get("id")) == str(nathan_id):
            target = resolve_target(message, by_id, last_issue)
            if target:
                decisions.append(
                    Decision(
                        issue=target,
                        verdict=verdict,
                        source="text",
                        message_id=message["id"],
                        author_id=nathan_id,
                        content=message_text(message)[:200],
                        created_at=message.get("timestamp") or "",
                    )
                )
        # get /channels/{id}/messages returns reaction counts only, so a
        # reaction decision cannot name who reacted. ponytail: attribute
        # reactions to a user via GET /channels/{id}/messages/{id}/reactions/{emoji}
        # if a decision ever has to be pinned to someone other than Nathan.
        for reaction in message.get("reactions") or []:
            emoji = (reaction.get("emoji") or {}).get("name") or ""
            verdict = (
                "approve" if emoji in APPROVE_REACTIONS
                else "reject" if emoji in REJECT_REACTIONS
                else None
            )
            if verdict and int(reaction.get("count") or 0) > 0 and last_issue:
                decisions.append(
                    Decision(
                        issue=last_issue,
                        verdict=verdict,
                        source="reaction",
                        message_id=message["id"],
                        author_id=str((message.get("author") or {}).get("id") or ""),
                        content=emoji,
                        created_at=message.get("timestamp") or "",
                    )
                )
    return decisions


def fetch_messages(channel_id: str, token: str, before=None) -> list:
    url = f"{DISCORD_API}/channels/{channel_id}/messages?limit={PAGE}"
    if before:
        url += f"&before={before}"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def collect(channel_id: str, token: str, scanned: set, max_pages: int = 10) -> list:
    """Page backwards until an already-scanned message or max_pages, chronological."""
    messages = []
    before = None
    for _ in range(max_pages):
        batch = fetch_messages(channel_id, token, before=before)
        if not batch:
            break
        messages.extend(batch)
        if len(batch) < PAGE or scanned.intersection(m["id"] for m in batch):
            break
        before = batch[-1]["id"]
    messages.reverse()
    return messages


def pending(decisions: list, seen) -> list:
    """Decisions not yet recorded, so a repeated poll never applies one twice."""
    return [decision for decision in decisions if decision.key not in seen]


def load_state(path: str) -> dict:
    try:
        with open(path) as handle:
            state = json.load(handle)
        return {
            "seen": state.get("seen", {}),
            "messages": state.get("messages", []),
            "recorded": state.get("recorded", []),
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": {}, "messages": [], "recorded": []}


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def paperclip(method: str, path: str, api_url: str, api_key: str, body=None):
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def record(decision: Decision, api_url: str, api_key: str, company_id: str) -> str:
    """Post the decision on the Paperclip issue; status stays with the monitor owner."""
    found = paperclip(
        "GET",
        f"/api/companies/{company_id}/issues?q={decision.issue}",
        api_url,
        api_key,
    )
    issues = found if isinstance(found, list) else found.get("issues", found.get("items", []))
    match = next((i for i in issues if i.get("identifier") == decision.issue), None)
    if not match:
        return "no matching issue"
    paperclip(
        "POST",
        f"/api/issues/{match['id']}/comments",
        api_url,
        api_key,
        {
            "body": (
                f"Approval **{decision.verdict}** seen in #marketing from a "
                f"{decision.source} decision.\n\n"
                f"- Discord message: `{decision.message_id}`"
                f"{f' at {decision.created_at}' if decision.created_at else ''}\n"
                f"- Message: `{decision.content[:180]}`"
            )
        },
    )
    return f"commented on {decision.issue}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channel", default=os.getenv("DISCORD_CHANNEL_MARKETING",
                                                       DEFAULT_MARKETING_CHANNEL))
    parser.add_argument("--nathan-id", default=os.getenv("NATHAN_DISCORD_ID",
                                                         DEFAULT_NATHAN_ID))
    parser.add_argument("--state", default=os.getenv("APPROVAL_WATCHER_STATE",
                                                     DEFAULT_STATE))
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--apply", action="store_true",
                        help="record each new decision as a comment on its Paperclip issue")
    args = parser.parse_args()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("DISCORD_BOT_TOKEN is not set", file=sys.stderr)
        return 2

    state_path = os.path.expanduser(args.state)
    state = load_state(state_path)
    messages = collect(args.channel, token, set(state["messages"]), args.max_pages)
    decisions = scan(messages, args.nathan_id)

    applied = 0
    for decision in pending(decisions, state["seen"]):
        outcome = "detected"
        if args.apply:
            api_url = os.getenv("PAPERCLIP_API_URL", "")
            api_key = os.getenv("PAPERCLIP_API_KEY", "")
            company_id = os.getenv("PAPERCLIP_COMPANY_ID", "")
            if not (api_url and api_key and company_id):
                print("--apply needs PAPERCLIP_API_URL, PAPERCLIP_API_KEY, "
                      "PAPERCLIP_COMPANY_ID", file=sys.stderr)
                return 2
            try:
                outcome = record(decision, api_url, api_key, company_id)
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
                print(f"record failed for {decision.issue}: {exc}", file=sys.stderr)
                continue
        state["seen"][decision.key] = decision.created_at
        state["recorded"].append({**asdict(decision), "outcome": outcome})
        applied += 1
        print(json.dumps(asdict(decision)))

    state["messages"] = sorted({*state["messages"], *(m["id"] for m in messages)})
    save_state(state_path, state)
    print(json.dumps({"messages": len(messages), "decisions": len(decisions),
                      "new": applied, "channel": args.channel}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())