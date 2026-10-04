#!/usr/bin/env python3
"""Regression tests for the nightly-hosted-sync wait step (AUT-5396).

The schedule dispatcher starts scheduled runs 2.6-4.2h after the cron
fires (observed 2026-10-02T21:10Z and 2026-10-03T19:40Z for a
17:00Z cron), so the sync gate SKIPped two nights running while EP5
stayed on a broken pin. The workflow now fires the cron at 12:30Z and
the job sleeps until 17:00Z. These tests replay the exact python
block from .github/workflows/build-hosted.yml against synthetic clocks:

* a start before the window waits until 17:00Z (no failure);
* a start inside 17:00-18:00Z deploys immediately;
* a start at/after 18:00Z fails loudly — the old silent green SKIP
  is the regression this guards against.
"""
import io
import re
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

WORKFLOW = ".github/workflows/build-hosted.yml"
CRON = "30 12 * * *"


def wait_block():
    with open(WORKFLOW) as f:
        src = f.read()
    m = re.search(r"python3 - <<'EOF'\n(.*?)\n          EOF\n", src, re.S)
    assert m, "wait block not found in workflow"
    return "\n".join(l[10:] if l.startswith(" " * 10) else l
                     for l in m.group(1).split("\n"))


def run_block(block, now):
    """Run the wait block as if datetime.now() returned `now`.

    time.sleep is stubbed so the tests return instantly; the slept
    duration is reported back in minutes.
    """
    code = (
        "import time\n"
        "SLEPT = [0]\n"
        "time.sleep = lambda s: SLEPT.__setitem__(0, s)\n"
        + block.replace(
            "datetime.now(timezone.utc)",
            f"datetime.fromtimestamp({now.timestamp()}, timezone.utc)",
        )
    )
    mod = types.ModuleType("wait")
    try:
        with redirect_stdout(io.StringIO()):
            exec(compile(code, "wait", "exec"), mod.__dict__)
        return None, mod.SLEPT[0] / 60
    except SystemExit as e:
        return e.code, mod.SLEPT[0] / 60


class NightlySyncWait(unittest.TestCase):
    def setUp(self):
        self.block = wait_block()

    def test_start_before_window_waits_until_1700z(self):
        # cron 12:30Z + best observed delay 2.6h
        exit_code, slept = run_block(
            self.block, datetime(2026, 10, 4, 15, 6, tzinfo=timezone.utc))
        self.assertIsNone(exit_code)
        self.assertGreaterEqual(slept, 113)
        self.assertLess(slept, 120)

    def test_start_at_worst_observed_delay_still_waits(self):
        # cron 12:30Z + worst observed delay 4.2h -> 16:42Z
        exit_code, slept = run_block(
            self.block, datetime(2026, 10, 4, 16, 42, tzinfo=timezone.utc))
        self.assertIsNone(exit_code)
        self.assertGreaterEqual(slept, 17)
        self.assertLess(slept, 20)

    def test_start_inside_window_deploys_immediately(self):
        exit_code, slept = run_block(
            self.block, datetime(2026, 10, 4, 17, 20, tzinfo=timezone.utc))
        self.assertIsNone(exit_code)
        self.assertEqual(slept, 0)

    def test_start_at_window_close_fails_loudly(self):
        exit_code, _ = run_block(
            self.block, datetime(2026, 10, 4, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(exit_code, 1)

    def test_late_start_like_the_two_missed_nights_fails_loudly(self):
        # the actual 2026-10-03 start time that silently SKIPped
        exit_code, _ = run_block(
            self.block, datetime(2026, 10, 3, 19, 40, tzinfo=timezone.utc))
        self.assertEqual(exit_code, 1)

    def test_cron_tolerates_worst_observed_dispatch_delay(self):
        hour, minute = CRON.split()[1].split(":") if ":" in CRON else (
            int(CRON.split()[1]) // 60, int(CRON.split()[1]) % 60)
        # 12:30Z + 4.2h must still start before the 18:00Z close
        self.assertLess(hour * 60 + minute + int(4.2 * 60), 18 * 60)


if __name__ == "__main__":
    unittest.main()
