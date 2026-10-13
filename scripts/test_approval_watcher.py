#!/usr/bin/env python3
"""AUT-4535 / AUT-5450: approval decisions in #marketing must be detected.

AUT-3989 and AUT-4507 were approved by Nathan in text in #marketing and never
seen, because approval monitoring only read emoji reactions. These tests pin the
text path (and keep the reaction path working), cover the target resolution the
watcher needs for approval tasks already posted to the channel (AUT-4555), and
prove a second poll cannot apply the same decision twice.

The offline fixtures reuse the wording of the four real decisions recorded on
AUT-4555 ("Approved", "I approve all", "All posts are approved", "Approve all")
so the offline tests exercise the strings that actually missed the monitors.
"""
import importlib.util
import json
import os
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "approval_watcher.py")

spec = importlib.util.spec_from_file_location("approval_watcher", SCRIPT)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)

NATHAN = "132444441024790529"
BOT = "1535541293969838080"


def message(author, content, msg_id, **extra):
    base = {
        "id": msg_id,
        "author": {"id": author},
        "content": content,
        "timestamp": "2026-08-01T10:00:00.000000+00:00",
    }
    base.update(extra)
    return base


def approval_request(issue, msg_id, embed=True):
    """A bot post asking for approval of an issue, the way #marketing gets them."""
    body = {"title": f"Approval needed: {issue}", "description": f"Reply to approve {issue}."}
    extra = {"embeds": [body]} if embed else {"content": body["description"]}
    return message(BOT, "", msg_id, **extra)


class TextApprovalDetection(unittest.TestCase):
    def test_text_approval_in_marketing_is_detected(self):
        """The regression: Nathan's "Approved" text must produce a decision."""
        messages = [
            approval_request("AUT-3989", "1001"),
            message(NATHAN, "Approved", "1002"),
        ]
        decisions = watcher.scan(messages, NATHAN)
        self.assertEqual(len(decisions), 1, decisions)
        self.assertEqual(decisions[0].issue, "AUT-3989")
        self.assertEqual(decisions[0].verdict, "approve")
        self.assertEqual(decisions[0].source, "text")

    def test_real_recorded_approvals_are_detected(self):
        """The four decisions from AUT-4555, in the wording Nathan actually used."""
        for content in ("Approved", "I approve all", "All posts are approved", "Approve all"):
            with self.subTest(content=content):
                decisions = watcher.scan(
                    [approval_request("AUT-4422", "2001"), message(NATHAN, content, "2002")],
                    NATHAN,
                )
                self.assertEqual([d.verdict for d in decisions], ["approve"])
                self.assertEqual([d.issue for d in decisions], ["AUT-4422"])

    def test_rejection_words(self):
        for content, verdict in (
            ("No", "reject"),
            ("nope", "reject"),
            ("reject", "reject"),
            ("block it", "reject"),
            ("hold off", "reject"),
            ("not yet", "reject"),
            ("do not ship", "reject"),
            ("Yes", "approve"),
            ("ship it", "approve"),
            ("lgtm", "approve"),
        ):
            with self.subTest(content=content):
                self.assertEqual(watcher.classify_text(content), verdict)

    def test_negated_approval_is_a_rejection(self):
        for content in ("not approved", "I don't approve", "do not approve this"):
            with self.subTest(content=content):
                self.assertEqual(watcher.classify_text(content), "reject")

    def test_non_decision_text_is_ignored(self):
        for content in ("", "sure thing, will review tomorrow", "hold on, one more question"):
            with self.subTest(content=content):
                self.assertIsNone(watcher.classify_text(content))

    def test_only_nathan_counts_as_the_decision_author(self):
        messages = [
            approval_request("AUT-3989", "3001"),
            message(BOT, "Approved", "3002"),
            message("999999999999999999", "Approved", "3003"),
            message(NATHAN, "looks good, no rush", "3004"),
        ]
        self.assertEqual(watcher.scan(messages, NATHAN), [])


class TargetResolution(unittest.TestCase):
    def test_reply_to_approval_request_resolves_the_issue(self):
        messages = [
            approval_request("AUT-4507", "4001"),
            message(NATHAN, "Approved", "4002", message_reference={"message_id": "4001"}),
        ]
        self.assertEqual([d.issue for d in watcher.scan(messages, NATHAN)], ["AUT-4507"])

    def test_preceding_bot_message_resolves_the_issue(self):
        messages = [
            approval_request("AUT-4260", "5001"),
            message(NATHAN, "I approve all", "5002"),
        ]
        self.assertEqual([d.issue for d in watcher.scan(messages, NATHAN)], ["AUT-4260"])

    def test_issue_named_in_the_message_wins(self):
        messages = [
            approval_request("AUT-4260", "6001"),
            approval_request("AUT-4507", "6002"),
            message(NATHAN, "AUT-4507 approved", "6003"),
        ]
        self.assertEqual([d.issue for d in watcher.scan(messages, NATHAN)], ["AUT-4507"])

    def test_decision_without_any_approval_context_is_dropped(self):
        messages = [message(NATHAN, "Approved", "7001")]
        self.assertEqual(watcher.scan(messages, NATHAN), [])


class ReactionPathStillWorks(unittest.TestCase):
    def test_approval_reaction_is_still_a_decision(self):
        messages = [
            approval_request("AUT-3989", "8001"),
            message(NATHAN, "Approved", "8002",
                    reactions=[{"emoji": {"name": "✅"}, "count": 2}]),
        ]
        decisions = watcher.scan(messages, NATHAN)
        self.assertEqual({d.source for d in decisions}, {"text", "reaction"})
        self.assertEqual({d.verdict for d in decisions}, {"approve"})

    def test_rejection_reaction(self):
        messages = [
            approval_request("AUT-3989", "8101"),
            message(NATHAN, "❌", "8102",
                    reactions=[{"emoji": {"name": "❌"}, "count": 1}]),
        ]
        decisions = watcher.scan(messages, NATHAN)
        self.assertEqual([d.verdict for d in decisions if d.source == "reaction"], ["reject"])

    def test_zero_count_reaction_is_not_a_decision(self):
        messages = [
            approval_request("AUT-3989", "8201"),
            message(NATHAN, "still reading", "8202",
                    reactions=[{"emoji": {"name": "✅"}, "count": 0}]),
        ]
        self.assertEqual(watcher.scan(messages, NATHAN), [])


class Idempotency(unittest.TestCase):
    def setUp(self):
        self.messages = [
            approval_request("AUT-4507", "9001"),
            message(NATHAN, "Approved", "9002"),
        ]
        self.decisions = watcher.scan(self.messages, NATHAN)

    def test_second_poll_of_the_same_messages_applies_nothing(self):
        seen = {d.key: d.created_at for d in self.decisions}
        self.assertEqual(watcher.pending(self.decisions, seen), [])

    def test_state_file_round_trip_keeps_decisions_applied_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "state.json")
            state = watcher.load_state(path)
            self.assertEqual(state["seen"], {})
            fresh = watcher.pending(self.decisions, state["seen"])
            self.assertEqual(len(fresh), 1)
            state["seen"][fresh[0].key] = fresh[0].created_at
            state["messages"] = [m["id"] for m in self.messages]
            watcher.save_state(path, state)
            reloaded = watcher.load_state(path)
            self.assertEqual(watcher.pending(self.decisions, reloaded["seen"]), [])
            self.assertEqual(set(reloaded["messages"]), {"9001", "9002"})

    def test_corrupt_state_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as handle:
                handle.write("{not json")
            self.assertEqual(watcher.pending(self.decisions, watcher.load_state(path)["seen"]),
                             self.decisions)


class LiveMarketingChannel(unittest.TestCase):
    """Opt-in: run with DISCORD_BOT_TOKEN to read the real channel."""

    def test_real_marketing_channel_has_detectable_text_approvals(self):
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            self.skipTest("DISCORD_BOT_TOKEN not set")
        channel = os.getenv("DISCORD_CHANNEL_MARKETING", watcher.DEFAULT_MARKETING_CHANNEL)
        nathan = os.getenv("NATHAN_DISCORD_ID", watcher.DEFAULT_NATHAN_ID)
        messages = watcher.collect(channel, token, set(), max_pages=5)
        self.assertTrue(messages, f"no messages read from #{channel}")
        decisions = watcher.scan(messages, nathan)
        print(json.dumps([watcher.asdict(d) for d in decisions], indent=2))
        self.assertTrue(
            [d for d in decisions if d.source == "text"],
            "no text approval detected in the live #marketing history",
        )


if __name__ == "__main__":
    unittest.main()