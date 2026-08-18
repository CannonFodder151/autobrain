/// Dongle BLE provisioning — facade over the platform implementation.
///
/// The esp32-diy board exposes service 6E400001-B5A3-F393-E0A9-E50E24DCCA9E:
/// characteristic 6E400003 accepts the one-shot provisioning JSON (compact,
/// see dongle_provisioning.dart) and replies "ok" / "err:…" on the SAME
/// characteristic, which we read to confirm. Web/desktop get a no-op stub via
/// the conditional import, so the web build never links the BLE plugin.
library;

import 'package:flutter/foundation.dart';

import 'dongle_ble_stub.dart'
    if (dart.library.io) 'dongle_ble_io.dart' as impl;

class DongleBle {
  /// Whether this platform can provision the dongle over BLE (mobile only).
  static bool get supported => impl.BleImpl.supported;

  /// Scans for every AutoBrain-Tripper peripheral in range and returns its
  /// identity (name + remoteId) so the user can confirm WHICH dongle receives
  /// the provisioning write (AUT-966). Throws [DongleBleException] with a
  /// user-facing message when none are found.
  static Future<List<DonglePeripheral>> scan() =>
      (scanOverride ?? impl.BleImpl.scan)();

  /// Writes [payload] ONLY to the peripheral whose remoteId equals
  /// [deviceId] (the user-confirmed dongle) and returns the firmware's ack
  /// string ("ok" or "err:…"). Never auto-picks a device. Throws
  /// [DongleBleException] with a user-facing message when the confirmed
  /// dongle cannot be reached or does not ack in time.
  static Future<String> provision(String payload,
          {required String deviceId}) =>
      (provisionOverride ?? impl.BleImpl.provision)(payload, deviceId);

  /// Test seams (AUT-966): swap in fakes so widget tests never touch the BLE
  /// plugin. Reset to null in tearDown.
  @visibleForTesting
  static Future<List<DonglePeripheral>> Function()? scanOverride;
  @visibleForTesting
  static Future<String> Function(String payload, String deviceId)?
      provisionOverride;
}

/// Identity of a discovered dongle, surfaced for explicit user confirmation
/// before the provisioning write. [deviceId] is the BLE remoteId (MAC).
class DonglePeripheral {
  const DonglePeripheral({required this.deviceId, required this.name});

  final String deviceId;
  final String name;

  @override
  String toString() => '$name ($deviceId)';
}

class DongleBleException implements Exception {
  final String message;
  DongleBleException(this.message);
  @override
  String toString() => message;
}
