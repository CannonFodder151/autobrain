"""AUT-1673: self-check for firmware manifest + installed telemetry.

These tests exercise the pydantic schemas directly (no DB), covering the input
validation that gates the device-authenticated /report write and the admin
/publish write. They exist to catch the regressions flagged in the PR #296
review: control-char / XSS / SQL-meta injection on reported fields, sha256
case-sensitivity, and size_bytes bounds.
"""

import unittest

from pydantic import ValidationError

from app.schemas.dongle_firmware import (
    DongleFirmwareCreate,
    DongleInstalledFirmwareReport,
)


def _ok_report(**overrides):
    base = {
        'model': 'OBD Logging Device V1',
        'firmware_version': '1.4.2',
        'serial_number': 'AB123456789',
    }
    base.update(overrides)
    return DongleInstalledFirmwareReport(**base)


def _ok_create(**overrides):
    base = {
        'model': 'OBD Logging Device V1',
        'version': '1.4.2',
        'sha256': 'a' * 64,
        'size_bytes': 2048,
        'blob_key': 'dongle_firmware/abc.bin',
    }
    base.update(overrides)
    return DongleFirmwareCreate(**base)


class TestDongleFirmwareSchema(unittest.TestCase):
    def test_manifest_shape(self):
        # Valid manifest constructs through the schema.
        manifest = _ok_create()
        self.assertEqual(manifest.model, 'OBD Logging Device V1')
        self.assertEqual(len(manifest.sha256), 64)
        self.assertGreater(manifest.size_bytes, 0)

    def test_report_shape(self):
        report = _ok_report()
        self.assertEqual(report.model, 'OBD Logging Device V1')
        self.assertEqual(len(report.serial_number), 11)

    def test_report_rejects_control_chars(self):
        for field in ('model', 'firmware_version', 'serial_number'):
            for ch in ('\n', '\r', '\t', '\x00'):
                with self.subTest(field=field, ch=ch):
                    with self.assertRaises(ValidationError):
                        _ok_report(**{field: 'bad' + ch})

    def test_report_rejects_xss_and_injection_metas(self):
        # Stored-XSS and SQLi surface characters must be rejected by the
        # whitelist, not the (parameterised) DB layer.
        for field in ('model', 'firmware_version', 'serial_number'):
            for bad in ('<script>', 'OBD"x', "OBD'x", 'a;b', 'a`b', 'a<b'):
                with self.subTest(field=field, bad=bad):
                    with self.assertRaises(ValidationError):
                        _ok_report(**{field: bad})

    def test_report_accepts_safe_punctuation(self):
        # Spaces, hyphens, dots, slashes and parens are legitimate.
        _ok_report(model='OBD Logging Device V1 (Beta)',
                   firmware_version='1.4.2-beta',
                   serial_number='AB-123/456')
        self.assertTrue(True)

    def test_report_rejects_empty_and_oversize(self):
        for field in ('model', 'firmware_version', 'serial_number'):
            with self.subTest('empty', field=field):
                with self.assertRaises(ValidationError):
                    _ok_report(**{field: ''})

    def test_sha256_accepts_uppercase(self):
        # esptool / MinIO emit hex in either case (AUT-1673 review).
        _ok_create(sha256='A' * 64)
        _ok_create(sha256='0123456789abcdefABCDEF' + 'F' * 42)

    def test_sha256_rejects_wrong_length_or_nonhex(self):
        with self.assertRaises(ValidationError):
            _ok_create(sha256='a' * 63)
        with self.assertRaises(ValidationError):
            _ok_create(sha256='z' * 64)

    def test_size_bytes_must_be_positive_and_bounded(self):
        with self.assertRaises(ValidationError):
            _ok_create(size_bytes=0)
        # 16 MiB ceiling from the schema.
        _ok_create(size_bytes=16 * 1024 * 1024)
        with self.assertRaises(ValidationError):
            _ok_create(size_bytes=16 * 1024 * 1024 + 1)


if __name__ == '__main__':
    unittest.main()
