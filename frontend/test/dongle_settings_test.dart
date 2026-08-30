// Regression tests for AUT-963 F1: logout / server switch must clear the
// dongle credential stores so a previous account's device key + WiFi password
// can never be pushed from another account.

import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/services/dongle/dongle_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Map<String, String> secure;

  setUp(() {
    secure = {
      'dongle_wifi_pass': 'wifi-secret',
      'dongle_api_key': 'abdev_old-account',
    };
    SharedPreferences.setMockInitialValues({
      'dongle_wifi_enabled': true,
      'dongle_wifi_ssid': 'Home',
      'dongle_device_id': 'dev-1',
      'dongle_device_name': 'Tripper',
      'dongle_vehicle_id': 'v9',
      'dark_mode': true,
    });
    FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform(secure);
  });

  test('clear removes secure credentials and all dongle prefs', () async {
    await DongleSettings.clear();

    expect(secure.containsKey('dongle_wifi_pass'), isFalse);
    expect(secure.containsKey('dongle_api_key'), isFalse);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getKeys().where((k) => k.startsWith('dongle_')), isEmpty);
    expect(prefs.getBool('dark_mode'), isTrue, reason: 'non-dongle prefs survive');
  });

  test('logout clears both dongle stores', () async {
    final state = AuthState();
    await state.logout();

    expect(secure.containsKey('dongle_wifi_pass'), isFalse);
    expect(secure.containsKey('dongle_api_key'), isFalse);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getKeys().where((k) => k.startsWith('dongle_')), isEmpty);
  });
}
