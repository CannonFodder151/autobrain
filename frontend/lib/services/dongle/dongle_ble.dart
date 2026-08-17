/// Dongle BLE provisioning — facade over the platform implementation.
///
/// The esp32-diy board exposes service 6E400001-B5A3-F393-E0A9-E50E24DCCA9E:
/// characteristic 6E400003 accepts the one-shot provisioning JSON (compact,
/// see dongle_provisioning.dart) and replies "ok" / "err:…" on the SAME
/// characteristic, which we read to confirm. Web/desktop get a no-op stub via
/// the conditional import, so the web build never links the BLE plugin.
library;

import 'dongle_ble_stub.dart'
    if (dart.library.io) 'dongle_ble_io.dart' as impl;

class DongleBle {
  /// Whether this platform can provision the dongle over BLE (mobile only).
  static bool get supported => impl.BleImpl.supported;

  /// Scans for the AutoBrain-Tripper peripheral, writes [payload] to the
  /// provisioning characteristic and returns the firmware's ack string
  /// ("ok" or "err:…"). Throws [DongleBleException] with a user-facing
  /// message when the dongle cannot be reached or does not ack in time.
  static Future<String> provision(String payload) =>
      impl.BleImpl.provision(payload);
}

class DongleBleException implements Exception {
  final String message;
  DongleBleException(this.message);
  @override
  String toString() => message;
}
