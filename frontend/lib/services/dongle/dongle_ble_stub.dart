/// No-op BLE provisioning for platforms without the plugin (web/desktop).
/// See [dongle_ble_io.dart] for the flutter_blue_plus implementation.
library;

import 'dongle_ble.dart';

class BleImpl {
  static bool get supported => false;

  /// BLE never ships on web/desktop (no flutter_blue_plus plugin), and OTA is
  /// not implemented on mobile yet — both report false so the facade can gate.
  static bool get isOtaAvailable => false;

  static Future<List<DonglePeripheral>> scan() {
    throw DongleBleException('BLE provisioning is only supported on the app.');
  }

  static Future<String> provision(String payload, {required String deviceId}) {
    throw DongleBleException('BLE provisioning is only supported on the app.');
  }

  static Future<DongleSyncResult> sync(String deviceId) {
    throw DongleBleException('Dongle sync is only supported on the app.');
  }

  static Future<void> clearCodes(String deviceId) {
    throw DongleBleException('Dongle sync is only supported on the app.');
  }

  static Future<({String model, String firmwareVersion, String serialNumber})>
      readDeviceInfo(String deviceId) {
    throw DongleBleException(
        'Device info read is only supported on the mobile app.');
  }

  static Future<void> applyOta(String deviceId, List<int> blob) {
    throw DongleBleException('OTA update is only supported on the mobile app.');
  }
}
