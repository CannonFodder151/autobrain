/// flutter_blue_plus provisioning of the AutoBrain-Tripper dongle (AUT-936).
///
/// Wire format is fixed by the esp32-diy firmware (AUT-918): service
/// 6E400001, read/notify characteristic 6E400002 (trip index), write
/// characteristic 6E400003 (provisioning). The firmware writes its ack
/// ("ok" / "err:…") back to the SAME 6E400003 characteristic, so we subscribe
/// to notifications there, write the compact payload, and read the reply.
/// The ack is best-effort (AUT-968 F1): firmware from AUT-918 delivers it via
/// NOTIFY (fixed in the AUT-968 firmware PR), but a completed WRITE is already
/// success — we never block long on a reply that older firmware cannot send.
///
/// Package choice: flutter_blue_plus 1.32.8 (BSD-3). The 2.x line moved to a
/// paid commercial license for connect(), which a commercial app must not use.
/// 1.32.8 auto-requests BLUETOOTH_SCAN/CONNECT (Android 12+) and
/// ACCESS_FINE_LOCATION (Android 11-) on scan, so no extra permission plumbing
/// is needed here beyond the manifest entries.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'dongle_ble.dart';
import 'dongle_provisioning.dart';

const _serviceUuid = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E';
const _provisionCharUuid = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E';
// One-shot provisioning token (AUT-969 F2): firmware mints a fresh random
// token when the provisioning window opens; the app must READ it here and echo
// it back as prov_token in the payload or the write is rejected. Older
// firmware does not expose this characteristic — then we just proceed (the
// old board doesn't require the token).
const _tokenCharUuid = '6E400004-B5A3-F393-E0A9-E50E24DCCA9E';
// AUT-1573: trip-file pull + DTC snapshot/clear.
const _tripReadCharUuid = '6E400005-B5A3-F393-E0A9-E50E24DCCA9E';
const _dtcCharUuid = '6E400006-B5A3-F393-E0A9-E50E24DCCA9E';
// Must stay below the firmware's TRIP_CHUNK_MAX (460).
const _chunkSize = 440;
const _maxTripBytes = 2 * 1024 * 1024; // sanity cap per trip CSV
const _scanTimeout = Duration(seconds: 15);
// Ack wait: fixed firmware notifies in milliseconds, so 8s is ample; older
// firmware cannot notify at all and we must not block a success on it.
const _provisionTimeout = Duration(seconds: 8);
const _peripheralHint = 'AutoBrain-Tripper';

class BleImpl {
  static bool get supported =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  /// Provision the dongle over BLE and return the firmware ack ("ok" or
  /// "err:…"). Writes ONLY to the peripheral whose remoteId matches
  /// [deviceId] — the identity the user explicitly confirmed (AUT-966); the
  /// app never auto-picks a device from the scan. Throws [DongleBleException]
  /// with a user-facing message.
  static Future<String> provision(String payload,
      {required String deviceId}) async {
    if (!supported) {
      throw DongleBleException(
          'BLE provisioning is only available in the mobile app.');
    }
    final device = await _findDongle(deviceId);
    BluetoothCharacteristic? char;
    String? token;
    try {
      await device.connect(timeout: const Duration(seconds: 15));
      final services = await device.discoverServices();
      for (final s in services) {
        if (s.uuid.toString().toUpperCase() == _serviceUuid) {
          for (final c in s.characteristics) {
            final uuid = c.uuid.toString().toUpperCase();
            if (uuid == _provisionCharUuid) {
              char = c;
            } else if (uuid == _tokenCharUuid) {
              // AUT-969 F2: read the one-shot provisioning token (if the
              // firmware exposes it) so it can be echoed in the payload.
              token = await _readToken(c);
            }
          }
        }
      }
      if (char == null) {
        throw DongleBleException(
            'Dongle found, but it did not expose the AutoBrain provisioning '
            'service. Is this an AutoBrain-Tripper?');
      }
      // Subscribe, write, then read the ack. The ack is best-effort: on fixed
      // firmware the reply arrives in ms; if no reply comes (older firmware
      // without NOTIFY, or a dropped notification) the WRITE completing is
      // success on its own — surface any err: we DO hear, never block 25s.
      final ackFuture = char.onValueReceived
          .timeout(_provisionTimeout)
          .first
          .then((v) => utf8.decode(v).trim())
          .catchError((_) => '');
      await char.setNotifyValue(true);
      await char.write(utf8.encode(appendProvisionToken(payload, token)));
      final ack = await ackFuture;
      if (ack.startsWith('err:')) {
        throw DongleBleException(provisionAckMessage(ack));
      }
      return ack.isEmpty ? 'ok' : ack;
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

  /// Reads the one-shot provisioning token value (AUT-969 F2). A read failure
  /// is non-fatal: older firmware has no token characteristic, and the write
  /// is then attempted without an echo.
  static Future<String?> _readToken(BluetoothCharacteristic c) async {
    try {
      final v = await c.read(timeout: 5);
      final s = utf8.decode(v).trim();
      return s.isEmpty ? null : s;
    } catch (_) {
      return null;
    }
  }

  /// Scans for every matching dongle and returns its identity (name +
  /// remoteId) for the user to confirm before any write (AUT-966). Throws a
  /// user-facing error when none are found.
  static Future<List<DonglePeripheral>> scan() async {
    final seen = await _scanResults();
    final dongles = <String, ScanResult>{};
    for (final r in seen) {
      if (_isDongle(r)) {
        dongles[r.device.remoteId.str] = r;
      }
    }
    if (dongles.isEmpty) {
      throw DongleBleException(
          'No $_peripheralHint dongle found. Make sure it is powered on and '
          'in range, then try again.');
    }
    return [
      for (final r in dongles.values)
        DonglePeripheral(
          deviceId: r.device.remoteId.str,
          name: _displayName(r),
        ),
    ];
  }

  /// AUT-1573: connects to the confirmed dongle, pulls the trip index, every
  /// completed trip CSV and the stored DTC snapshot. Older firmware without
  /// the sync characteristics returns empty results instead of failing —
  /// provisioning still works on those boards.
  static Future<DongleSyncResult> sync(String deviceId) async {
    if (!supported) {
      throw DongleBleException(
          'Dongle sync is only available in the mobile app.');
    }
    final device = await _findDongle(deviceId);
    try {
      await device.connect(timeout: const Duration(seconds: 15));
      final services = await device.discoverServices();
      BluetoothCharacteristic? list, tripRead, dtc;
      for (final s in services) {
        if (s.uuid.toString().toUpperCase() != _serviceUuid) continue;
        for (final c in s.characteristics) {
          final uuid = c.uuid.toString().toUpperCase();
          if (uuid == '6E400002-B5A3-F393-E0A9-E50E24DCCA9E') list = c;
          if (uuid == _tripReadCharUuid) tripRead = c;
          if (uuid == _dtcCharUuid) dtc = c;
        }
      }
      final result = DongleSyncResult();
      if (list != null && tripRead != null) {
        final index = await _readText(list);
        for (final name in index.split('\n')) {
          final trip = name.trim();
          if (trip.isEmpty || !trip.endsWith('.csv')) continue;
          result.trips[trip] = await _pullTrip(tripRead, trip);
        }
      }
      if (dtc != null) result.dtc = await _readText(dtc);
      return result;
    } on DongleBleException {
      rethrow;
    } catch (e) {
      throw DongleBleException('Could not sync with the dongle: $e');
    } finally {
      if (device.isConnected) {
        await device.disconnect().catchError((_) {});
      }
    }
  }

  /// Pulls one trip CSV in chunks: write "<name>@<offset>", read the chunk,
  /// repeat until a short/empty chunk arrives.
  static Future<String> _pullTrip(
      BluetoothCharacteristic c, String name) async {
    final buffer = BytesBuilder(copy: false);
    var offset = 0;
    while (offset < _maxTripBytes) {
      await c.write(utf8.encode('$name@$offset'));
      final chunk = await c.read();
      if (chunk.isEmpty) break;
      buffer.add(chunk);
      offset += chunk.length;
      if (chunk.length < _chunkSize) break;
    }
    return utf8.decode(buffer.takeBytes(), allowMalformed: true);
  }

  /// AUT-1573: asks the dongle to clear car codes (mode 04). Throws with the
  /// firmware's reason when it refuses ("err:no can bus" while parked, etc).
  static Future<void> clearCodes(String deviceId) async {
    if (!supported) {
      throw DongleBleException(
          'Dongle sync is only available in the mobile app.');
    }
    final device = await _findDongle(deviceId);
    try {
      await device.connect(timeout: const Duration(seconds: 15));
      BluetoothCharacteristic? dtc;
      for (final s in await device.discoverServices()) {
        if (s.uuid.toString().toUpperCase() != _serviceUuid) continue;
        for (final c in s.characteristics) {
          if (c.uuid.toString().toUpperCase() == _dtcCharUuid) dtc = c;
        }
      }
      if (dtc == null) {
        throw DongleBleException(
            'This dongle firmware does not support code clearing yet. '
            'Update the board firmware first.');
      }
      await dtc.write(utf8.encode('clear'));
      final ack = utf8.decode(await dtc.read()).trim();
      if (ack.startsWith('err:') || ack.isEmpty) {
        throw DongleBleException(ack.isEmpty
            ? 'The dongle did not confirm the clear.'
            : provisionAckMessage(ack));
      }
    } on DongleBleException {
      rethrow;
    } catch (e) {
      throw DongleBleException('Could not clear codes: $e');
    } finally {
      if (device.isConnected) {
        await device.disconnect().catchError((_) {});
      }
    }
  }

  static Future<String> _readText(BluetoothCharacteristic c) async {
    try {
      final v = await c.read();
      return utf8.decode(v, allowMalformed: true);
    } catch (_) {
      return '';
    }
  }

  /// Finds the ONE peripheral whose remoteId equals the user-confirmed
  /// [deviceId], or throws. BLE advertisement data is attacker-spoofable, so
  /// identity is keyed on the confirmed remoteId, never the first match.
  static Future<BluetoothDevice> _findDongle(String deviceId) async {
    final seen = await _scanResults();
    for (final r in seen) {
      if (r.device.remoteId.str == deviceId) return r.device;
    }
    throw DongleBleException(
        'The confirmed $_peripheralHint dongle is no longer in range. '
        'Power it on and try again.');
  }

  static Future<List<ScanResult>> _scanResults() async {
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
    return seen;
  }

  static bool _isDongle(ScanResult r) {
    final name = _advName(r).toLowerCase();
    final hasService = r.advertisementData.serviceUuids
        .any((u) => u.toString().toUpperCase() == _serviceUuid);
    return hasService || name.contains('autobrain');
  }

  static String _displayName(ScanResult r) {
    final name = _advName(r);
    return name.isEmpty ? _peripheralHint : name;
  }

  static String _advName(ScanResult r) {
    final adv = r.advertisementData.advName;
    return adv.isNotEmpty ? adv : r.device.platformName;
  }
}
