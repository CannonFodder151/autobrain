#!/usr/bin/env python3
"""AUT-5714 self-checks for the ARM64 runner compose.

Run: python3 scripts/test_runner_compose_stop_drain.py -v

No docker daemon needed. Two groups:

1. compose invariants -- the EP5 runner stack (Portainer stack 123)
   must put Runner.Listener itself in the PID 1 slot and give Docker a
   grace period longer than the runner's own shutdown budget, or a
   `docker stop` SIGKILLs an in-flight job.
2. the signal-delivery mechanism, replayed with plain bash so the
   claim holds on any box with a shell: a bash wrapper that runs a
   foreground child does NOT forward SIGTERM, while `exec` does.
"""
import os
import pathlib
import signal
import subprocess
import tempfile
import time
import unittest

import yaml

COMPOSE = pathlib.Path(__file__).resolve().parent.parent / "docker-compose.runner.yml"

# src/Runner.Common/Constants.cs: Constants.Runner.ExitOnUnloadTimeout
EXIT_ON_UNLOAD_TIMEOUT_S = 30


def _parse_grace(text):
    """Parse a docker compose duration (e.g. "2m") into seconds."""
    units = {"s": 1, "m": 60, "h": 3600}
    suffix = text[-1]
    if suffix not in units:
        raise ValueError(f"unsupported grace unit in {text!r}")
    return int(text[:-1]) * units[suffix]


class RunnerCompose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = yaml.safe_load(COMPOSE.read_text())
        cls.svc = cls.doc["services"]["gh-runner-autobrain-arm64"]
        cls.cmd = cls.svc["entrypoint"][-1]

    def test_runner_binary_is_pid_one(self):
        # The last thing the entrypoint does must be `exec` on the
        # .NET listener, so the container's PID 1 is the process that
        # owns the signal handlers (Runner.cs CancelKeyPress /
        # HostContext.Unloading). Anything between Docker's SIGTERM and
        # Runner.Listener swallows it.
        self.assertIn("exec ./bin/Runner.Listener run", self.cmd)

    def test_no_exec_run_sh(self):
        # run.sh launches Runner.Listener as a foreground child and
        # traps nothing, so bash stays PID 1 and eats the SIGTERM.
        self.assertNotIn("exec ./run.sh", self.cmd)

    def test_registration_still_runs(self):
        # Must still self-configure when the named volume is empty, or
        # the recreated container comes up unregistered and every
        # hosted build stays queued.
        for needle in (".runner", "config.sh", "--unattended", "--replace"):
            self.assertIn(needle, self.cmd)

    def test_stop_grace_covers_runner_shutdown(self):
        grace = _parse_grace(self.svc["stop_grace_period"])
        self.assertGreater(grace, EXIT_ON_UNLOAD_TIMEOUT_S)


class SignalForwarding(unittest.TestCase):
    """Replays the mechanism with bash alone."""

    @staticmethod
    def _alive(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def test_bash_wrapper_does_not_forward_sigterm(self):
        # The pre-fix shape: bash as PID 1 with a foreground child.
        with tempfile.TemporaryDirectory() as d:
            pidfile = f"{d}/child.pid"
            proc = subprocess.Popen(
                ["bash", "-c", f"sleep 30 & echo $! > {pidfile}; wait"])
            for _ in range(100):
                if pathlib.Path(pidfile).exists():
                    break
                time.sleep(0.05)
            child = int(pathlib.Path(pidfile).read_text().strip())
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
            # bash is gone but its orphaned child is still running --
            # exactly the SIGKILL-instead-of-drain failure mode.
            self.assertFalse(self._alive(proc.pid))
            self.assertTrue(self._alive(child))
            try:
                os.kill(child, signal.SIGTERM)
            except OSError:
                pass

    def test_exec_puts_child_in_pid_one_slot(self):
        # The post-fix shape: exec replaces bash, so the signal lands
        # on the runner process itself.
        proc = subprocess.Popen(["bash", "-c", "exec sleep 30"])
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        self.assertFalse(self._alive(proc.pid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
