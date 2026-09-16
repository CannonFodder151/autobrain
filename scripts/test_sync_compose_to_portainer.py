#!/usr/bin/env python3
"""Regression test for sync-compose-to-portainer.py output logging.

Verifies the script logs only essential metadata, not the API response body.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()