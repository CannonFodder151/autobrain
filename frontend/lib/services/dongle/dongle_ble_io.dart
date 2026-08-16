/// flutter_blue_plus provisioning of the AutoBrain-Tripper dongle (AUT-936).
///
/// Wire format is fixed by the esp32-diy firmware (AUT-918): service
/// 6E400001, read/notify characteristic 6E400002 (trip index), write
/// characteristic 6E400003 (provisioning). The firmware writes its ack
/// ("ok" / "err:…") back to the SAME 6E400003 characteristic, so we subscribe
/// to notifications there, write the compact payload, and read the reply.
///
/// Package choice: flutter_blue_plus 1.32.8 (BSD-3). The 2.x line moved to a
/// paid commercial license for connect(), which a commercial app must not use.
/// 1.32.8 auto-requests BLUETOOTH_SCAN/CONNECT (Android 12+) and
/// ACCESS_FINE_LOCATION (Android 11-) on scan, so no extra permission plumbing
/// is needed here beyond the manifest entries.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'dongle_ble.dart';

const _serviceUuid = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E';
const _provisionCharUuid = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E';
const _scanTimeout = Duration(seconds: 15);
const _provisionTimeout = Duration(seconds: 25);
const _peripheralHint = 'AutoBrain-Tripper';

class BleImpl {
  static bool get supported =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  /// Provision the dongle over BLE and return the firmware ack ("ok" or
  /// "err:…"). Throws [DongleBleException] with a user-facing message.
  static Future<String> provision(String payload) async {
    if (!supported) {
      throw DongleBleException(
          'BLE provisioning is only available in the mobile app.');
    }
    final device = await _findDongle();
    BluetoothCharacteristic? char;
    try {
      await device.connect(timeout: const Duration(seconds: 15));
      final services = await device.discoverServices();
      for (final s in services) {
        if (s.uuid.toString().toUpperCase() == _serviceUuid) {
          for (final c in s.characteristics) {
            if (c.uuid.toString().toUpperCase() == _provisionCharUuid) {
              char = c;
            }
          }
        }
      }
      if (char == null) {
        throw DongleBleException(
            'Dongle found, but it did not expose the AutoBrain provisioning '
            'service. Is this an AutoBrain-Tripper?');
      }
      final ack = char.onValueReceived.timeout(_provisionTimeout).first;
      await char.setNotifyValue(true);
      await char.write(utf8.encode(payload));
      return utf8.decode(await ack).trim();
    } on DongleBleException {
      rethrow;
    } catch (e) {
      throw DongleBleException(
          'Could not provision the dongle: ${e.toString().trim()}');
    } finally {
      if (device.isConnected) {
        await device.disconnect().catchError((_) {});
      }
    }
  }

  /// Scans for the dongle and returns it, or throws a user-facing error.
  static Future<BluetoothDevice> _findDongle() async {
    final seen = <ScanResult>[];
    final sub = FlutterBluePlus.scanResults.listen((rs) {
      seen
        ..clear()
        ..addAll(rs);
    });
    try {
      await FlutterBluePlus.startScan(
        timeout: _scanTimeout,
        withServices: [Guid(_serviceUuid)],
      );
      await FlutterBluePlus.isScanning
          .firstWhere((s) => !s)
          .timeout(_scanTimeout + const Duration(seconds: 2));
    } catch (e) {
      throw DongleBleException('Bluetooth scan failed: ${e.toString().trim()}');
    } finally {
      await sub.cancel();
    }
    final dongles = <String, BluetoothDevice>{};
    for (final r in seen) {
      final name = (r.advertisementData.advName.isNotEmpty
              ? r.advertisementData.advName
              : r.device.platformName)
          .toLowerCase();
      final hasService = r.advertisementData.serviceUuids
          .any((u) => u.toString().toUpperCase() == _serviceUuid);
      if (hasService || name.contains('autobrain')) {
        dongles[r.device.remoteId.str] = r.device;
      }
    }
    if (dongles.isEmpty) {
      throw DongleBleException(
          'No $_peripheralHint dongle found. Make sure it is powered on and '
          'in range, then try again.');
    }
    return dongles.values.first;
  }
}
