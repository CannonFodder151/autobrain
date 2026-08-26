"""AUT-1673: self-check for firmware manifest + installed telemetry."""

import unittest


class TestDongleFirmwareSchema(unittest.TestCase):
    def test_manifest_shape(self):
        manifest = {
            'model': 'OBD Logging Device V1',
            'version': '1.4.2',
            'sha256': 'a' * 64,
            'size_bytes': 2048,
            'blob_url': 'https://example.com/firmware.bin',
            'release_notes': 'First stable release',
        }
        self.assertEqual(manifest['model'], 'OBD Logging Device V1')
        self.assertEqual(len(manifest['sha256']), 64)
        self.assertGreater(manifest['size_bytes'], 0)

    def test_report_shape(self):
        report = {
            'model': 'OBD Logging Device V1',
            'firmware_version': '1.4.2',
            'serial_number': 'AB123456789',
        }
        self.assertEqual(report['model'], 'OBD Logging Device V1')
        self.assertEqual(len(report['serial_number']), 11)


if __name__ == '__main__':
    unittest.main()
