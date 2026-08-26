/// Dongle BLE provisioning — facade over the platform implementation.
///
/// The esp32-diy board exposes service 6E400001-B5A3-F393-E0A9-E50E24DCCA9E:
/// characteristic 6E400003 accepts the one-shot provisioning JSON (compact,
/// see dongle_provisioning.dart) and replies "ok" / "err:…" on the SAME
/// characteristic, which we read to confirm. Web/desktop get a no-op stub via
/// the conditional import, so the web build never links the BLE plugin.
library;

import 'package:flutter/foundation.dart';

import 'dongle_ble_stub.dart' if (dart.library.io) 'dongle_ble_io.dart' as impl;

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
  static Future<String> provision(String payload, {required String deviceId}) =>
      (provisionOverride ?? impl.BleImpl.provision)(payload, deviceId);

  /// AUT-1573: pulls the trip index, all completed trip CSVs and the stored
  /// DTC snapshot from the confirmed dongle.
  static Future<DongleSyncResult> sync(String deviceId) =>
      (syncOverride ?? impl.BleImpl.sync)(deviceId);

  /// AUT-1573: clears car codes on the confirmed dongle (firmware mode 04).
  static Future<void> clearCodes(String deviceId) =>
      (clearCodesOverride ?? impl.BleImpl.clearCodes)(deviceId);

  /// AUT-1673: reads model, firmware version and serial number over BLE.
  /// The result is not cached; caller should persist to backend via
  /// DongleFirmwareApi.reportInstalled for long-term storage.
  static Future<({String model, String firmwareVersion, String serialNumber})>
      readDeviceInfo(String deviceId) =>
          (readDeviceInfoOverride ?? impl.BleImpl.readDeviceInfo)(deviceId);

  /// AUT-1673: OTA update via BLE. The app verifies SHA-256 against the
  /// manifest first, then writes chunked firmware bytes to the dongle.
  static Future<void> applyOta(String deviceId, List<int> blob) =>
      (applyOtaOverride ?? impl.BleImpl.applyOta)(deviceId, blob);

  /// Test seams (AUT-966): swap in fakes so widget tests never touch the BLE
  /// plugin. Reset to null in tearDown.
  @visibleForTesting
  static Future<List<DonglePeripheral>> Function()? scanOverride;
  @visibleForTesting
  static Future<String> Function(String payload, String deviceId)?
      provisionOverride;
  @visibleForTesting
  static Future<DongleSyncResult> Function(String deviceId)? syncOverride;
  @visibleForTesting
  static Future<void> Function(String deviceId)? clearCodesOverride;
  @visibleForTesting
  static Future<({String model, String firmwareVersion, String serialNumber})>
          Function(String deviceId)?
      readDeviceInfoOverride;
  @visibleForTesting
  static Future<void> Function(String deviceId, List<int>)? applyOtaOverride;
}

/// Result of one BLE sync pass: completed-trip CSVs keyed by filename and the
/// current DTC text (empty when the board has none or old firmware).
class DongleSyncResult {
  final Map<String, String> trips = {};
  String dtc = '';
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
