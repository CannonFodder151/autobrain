/// No-op BLE provisioning for platforms without the plugin (web/desktop).
/// See [dongle_ble_io.dart] for the flutter_blue_plus implementation.
library;

import 'dongle_ble.dart';

class BleImpl {
  static bool get supported => false;

  static Future<List<DonglePeripheral>> scan() {
    throw DongleBleException('BLE provisioning is only supported on the app.');
  }

  static Future<String> provision(String payload, {required String deviceId}) {
    throw DongleBleException('BLE provisioning is only supported on the app.');
  }
}
