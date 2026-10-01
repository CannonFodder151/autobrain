#!/usr/bin/env python3
"""Regression test for sync-compose-to-portainer.py output logging.

Verifies the script logs only essential metadata, not the API response body.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from io import StringIO
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
    "sync_compose_to_portainer",
    os.path.join(os.path.dirname(__file__), "sync-compose-to-portainer.py"),
)
scp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scp)


class TestSyncComposeLogging(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.compose_file = os.path.join(self.temp_dir, "docker-compose.hosted.yml")
        with open(self.compose_file, "w") as f:
            f.write("version: '3.8'\nservices:\n  test:\n    image: test:latest\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("urllib.request.urlopen")
    def test_log_output_excludes_response_body(self, mock_urlopen):
        stacks_response = MagicMock()
        stacks_response.__enter__.return_value.read.return_value = json.dumps([
            {"Id": 42, "Name": "autobrain-hosted"}
        ]).encode()

        current_response = MagicMock()
        current_response.__enter__.return_value.read.return_value = json.dumps({
            "Env": [{"name": "TEST_VAR", "value": "test"}]
        }).encode()

        put_response = MagicMock()
        put_response.__enter__.return_value.read.return_value = json.dumps({
            "Id": 42,
            "SomeSensitiveData": "should-not-appear-in-logs"
        }).encode()

        mock_urlopen.side_effect = [stacks_response, current_response, put_response]

        captured = StringIO()
        sys.stdout = captured
        old_argv = sys.argv

        try:
            sys.argv = [
                "sync-compose-to-portainer.py",
                "--stack", "autobrain-hosted",
                "--endpoint", "5",
                "--file", self.compose_file,
                "--portainer-url", "https://portainer.example.com",
                "--api-key", "test-key",
            ]
            scp.main()
        finally:
            sys.stdout = sys.__stdout__
            sys.argv = old_argv

        output = captured.getvalue().strip()

        self.assertIn("stack=autobrain-hosted", output)
        self.assertIn("id=42", output)
        self.assertIn("endpoint=5", output)
        self.assertIn("updated", output)

        self.assertNotIn("SomeSensitiveData", output)
        self.assertNotIn("should-not-appear-in-logs", output)
        self.assertNotIn('{"Id": 42', output)

    @patch("urllib.request.urlopen")
    def test_env_read_from_stack_detail_not_file(self, mock_urlopen):
        """AUT-4778: env must come from GET /api/stacks/{id}, not /file."""
        stacks_response = MagicMock()
        stacks_response.__enter__.return_value.read.return_value = json.dumps([
            {"Id": 42, "Name": "autobrain-hosted"}
        ]).encode()

        # GET /api/stacks/42 — carries Env.
        detail_response = MagicMock()
        detail_response.__enter__.return_value.read.return_value = json.dumps({
            "Id": 42,
            "Env": [{"name": "POSTGRES_USER", "value": "autobrain"}],
        }).encode()

        put_response = MagicMock()
        put_response.__enter__.return_value.read.return_value = b"{}"

        mock_urlopen.side_effect = [stacks_response, detail_response, put_response]

        captured = StringIO()
        sys.stdout = captured
        old_argv = sys.argv
        try:
            sys.argv = [
                "sync-compose-to-portainer.py",
                "--stack", "autobrain-hosted",
                "--endpoint", "5",
                "--file", self.compose_file,
                "--portainer-url", "https://portainer.example.com",
                "--api-key", "test-key",
            ]
            self.assertEqual(scp.main(), 0)
        finally:
            sys.stdout = sys.__stdout__
            sys.argv = old_argv

        urls = [c.args[0].full_url for c in mock_urlopen.call_args_list
                if c.args and hasattr(c.args[0], "full_url")]
        self.assertIn("https://portainer.example.com/api/stacks/42", urls)
        self.assertNotIn("https://portainer.example.com/api/stacks/42/file", urls)

        put_call = mock_urlopen.call_args_list[-1]
        body = json.loads(put_call.args[0].data)
        self.assertEqual(body["Env"], [{"name": "POSTGRES_USER",
                                        "value": "autobrain"}])

    @patch("urllib.request.urlopen")
    def test_refuses_to_sync_when_env_empty(self, mock_urlopen):
        """AUT-4778: an empty env read means we would wipe the stack — bail."""
        stacks_response = MagicMock()
        stacks_response.__enter__.return_value.read.return_value = json.dumps([
            {"Id": 42, "Name": "autobrain-hosted"}
        ]).encode()

        detail_response = MagicMock()
        detail_response.__enter__.return_value.read.return_value = json.dumps(
            {"Id": 42, "Env": []}).encode()

        mock_urlopen.side_effect = [stacks_response, detail_response]

        err = StringIO()
        old_argv, old_err = sys.argv, sys.stderr
        try:
            sys.argv = [
                "sync-compose-to-portainer.py",
                "--stack", "autobrain-hosted",
                "--endpoint", "5",
                "--file", self.compose_file,
                "--portainer-url", "https://portainer.example.com",
                "--api-key", "test-key",
            ]
            sys.stderr = err
            self.assertEqual(scp.main(), 3)
        finally:
            sys.stderr = old_err
            sys.argv = old_argv

        self.assertIn("would wipe it", err.getvalue())
        self.assertEqual(len(mock_urlopen.call_args_list), 2)  # no PUT

    @patch("urllib.request.urlopen")
    def test_http_error_body_logged_with_env_values_redacted(self, mock_urlopen):
        """AUT-2998: the compose error must reach CI, minus stack secrets."""
        stacks_response = MagicMock()
        stacks_response.__enter__.return_value.read.return_value = json.dumps([
            {"Id": 42, "Name": "autobrain-hosted"}
        ]).encode()

        detail_response = MagicMock()
        detail_response.__enter__.return_value.read.return_value = json.dumps({
            "Id": 42,
            "Env": [{"name": "ADMIN_API_KEY", "value": "s3cr3t-token"}],
        }).encode()

        put_error = urllib.error.HTTPError(
            "https://portainer.example.com/api/stacks/42?endpointId=5",
            500, "Internal Server Error", {},
            io.BytesIO(
                b"service backend: POSTGRES_USER must be set; "
                b"ADMIN_API_KEY=s3cr3t-token"
            ),
        )

        mock_urlopen.side_effect = [stacks_response, detail_response, put_error]

        err = StringIO()
        old_argv, old_err = sys.argv, sys.stderr
        try:
            sys.argv = [
                "sync-compose-to-portainer.py",
                "--stack", "autobrain-hosted",
                "--endpoint", "5",
                "--file", self.compose_file,
                "--portainer-url", "https://portainer.example.com",
                "--api-key", "test-key",
            ]
            sys.stderr = err
            self.assertEqual(scp.main(), 1)
        finally:
            sys.stderr = old_err
            sys.argv = old_argv

        logged = err.getvalue()
        self.assertIn("500", logged)
        self.assertIn("POSTGRES_USER must be set", logged)
        self.assertNotIn("s3cr3t-token", logged)
        self.assertIn("***", logged)


if __name__ == "__main__":
    unittest.main()