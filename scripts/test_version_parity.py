#!/usr/bin/env python3
"""Unit tests for version_parity.py (AUT-5487 finding #3)."""
import json
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

import version_parity


class MockResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def read(self):
        return self.data
    
    def __iter__(self):
        return iter([self.data])


class TestVersionParity(unittest.TestCase):
    
    def test_extract_version_both_present(self):
        health = {"status": "ok", "version": "0.3.307", "env": "default"}
        version = {"app_name": "autobrain", "version": "0.3.307", "build_number": "304"}
        hv, vv = version_parity.extract_version(health, version)
        self.assertEqual(hv, "0.3.307")
        self.assertEqual(vv, "0.3.307")
    
    def test_extract_version_mismatch(self):
        health = {"status": "ok", "version": "0.3.307", "env": "default"}
        version = {"app_name": "autobrain", "version": "0.3.305", "build_number": "304"}
        hv, vv = version_parity.extract_version(health, version)
        self.assertEqual(hv, "0.3.307")
        self.assertEqual(vv, "0.3.305")
    
    def test_extract_version_missing_health_version(self):
        health = {"status": "ok", "env": "default"}
        version = {"app_name": "autobrain", "version": "0.3.305"}
        hv, vv = version_parity.extract_version(health, version)
        self.assertIsNone(hv)
        self.assertEqual(vv, "0.3.305")
    
    def test_extract_version_missing_version_json_version(self):
        health = {"status": "ok", "version": "0.3.307"}
        version = {"app_name": "autobrain", "build_number": "304"}
        hv, vv = version_parity.extract_version(health, version)
        self.assertEqual(hv, "0.3.307")
        self.assertIsNone(vv)
    
    def test_extract_version_none_inputs(self):
        hv, vv = version_parity.extract_version(None, None)
        self.assertIsNone(hv)
        self.assertIsNone(vv)
    
    @patch("version_parity.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen):
        mock_response = MockResponse(json.dumps({"version": "0.3.307"}).encode())
        mock_urlopen.return_value = mock_response
        
        result = version_parity.fetch_json("https://example.com/health")
        self.assertEqual(result, {"version": "0.3.307"})
    
    @patch("version_parity.urllib.request.urlopen")
    def test_fetch_json_404(self, mock_urlopen):
        mock_urlopen.side_effect = version_parity.urllib.error.HTTPError(
            "https://example.com/version.json", 404, "Not Found", {}, None
        )
        
        result = version_parity.fetch_json("https://example.com/version.json")
        self.assertIsNone(result)
    
    @patch("version_parity.urllib.request.urlopen")
    def test_fetch_json_invalid_json(self, mock_urlopen):
        mock_response = MockResponse(b"not json")
        mock_urlopen.return_value = mock_response
        
        result = version_parity.fetch_json("https://example.com/version.json")
        self.assertIsNone(result)
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_match(self, mock_fetch):
        mock_fetch.side_effect = [
            {"status": "ok", "version": "0.3.307", "env": "default"},
            {"app_name": "autobrain", "version": "0.3.307", "build_number": "304"},
        ]
        
        success, hv, vv = version_parity.check_version_parity("https://example.com/health")
        self.assertTrue(success)
        self.assertEqual(hv, "0.3.307")
        self.assertEqual(vv, "0.3.307")
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_mismatch(self, mock_fetch):
        mock_fetch.side_effect = [
            {"status": "ok", "version": "0.3.307", "env": "default"},
            {"app_name": "autobrain", "version": "0.3.305", "build_number": "304"},
        ]
        
        success, hv, vv = version_parity.check_version_parity("https://example.com/health")
        self.assertFalse(success)
        self.assertEqual(hv, "0.3.307")
        self.assertEqual(vv, "0.3.305")
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_missing_health_version(self, mock_fetch):
        mock_fetch.side_effect = [
            {"status": "ok", "env": "default"},
            {"app_name": "autobrain", "version": "0.3.305"},
        ]
        
        success, hv, vv = version_parity.check_version_parity("https://example.com/health")
        self.assertFalse(success)
        self.assertEqual(hv, "")
        self.assertEqual(vv, "0.3.305")
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_missing_version_json(self, mock_fetch):
        mock_fetch.side_effect = [
            {"status": "ok", "version": "0.3.307"},
            None,
        ]
        
        success, hv, vv = version_parity.check_version_parity("https://example.com/health", max_retries=1)
        self.assertFalse(success)
        self.assertEqual(hv, "0.3.307")
        self.assertEqual(vv, "")
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_retry_on_failure(self, mock_fetch):
        # First two attempts fail, third succeeds
        mock_fetch.side_effect = [
            {"status": "ok", "version": "0.3.307"},
            None,  # first attempt
            None,  # second attempt
            {"app_name": "autobrain", "version": "0.3.307"},  # third attempt
        ]
        
        success, hv, vv = version_parity.check_version_parity(
            "https://example.com/health", max_retries=3, retry_delay=0.01
        )
        self.assertTrue(success)
        self.assertEqual(mock_fetch.call_count, 4)  # 1 health + 3 version.json
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_path_prefix_handling(self, mock_fetch):
        # Health URL with path prefix (e.g., /api/health) should still work
        mock_fetch.side_effect = [
            {"status": "ok", "version": "0.3.307"},
            {"app_name": "autobrain", "version": "0.3.307"},
        ]
        
        success, hv, vv = version_parity.check_version_parity("https://example.com/api/health")
        self.assertTrue(success)
        # Verify version.json URL was derived correctly (stripping /api/health -> /api/version.json)
        # Actually the current implementation strips everything after the last /
        # Let's verify the call
        calls = mock_fetch.call_args_list
        self.assertEqual(calls[0][0][0], "https://example.com/api/health")
        self.assertEqual(calls[1][0][0], "https://example.com/api/version.json")
    
    @patch("version_parity.fetch_json")
    def test_check_version_parity_non_json_html_response(self, mock_fetch):
        # Simulate nginx 502 HTML error page
        mock_fetch.side_effect = [
            {"status": "ok", "version": "0.3.307"},
            None,  # HTML response returns None
        ]
        
        success, hv, vv = version_parity.check_version_parity("https://example.com/health", max_retries=1)
        self.assertFalse(success)
        self.assertEqual(hv, "0.3.307")
        self.assertEqual(vv, "")


if __name__ == "__main__":
    unittest.main()
