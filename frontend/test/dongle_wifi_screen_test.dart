// Regression tests for AUT-963 F1: "Push credentials" must be blocked when the
// saved device id is not present in the current account's device list, so the
// app can never provision a dongle with a previous account's key.

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/settings/dongle_wifi_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi(this.devices) : super(null);

  final List<Map<String, dynamic>> devices;

  @override
  Future<dynamic> get(String path) async {
    if (path == '/devices') return devices;
    if (path == '/vehicles') return const [];
    return null;
  }

  @override
  Future<dynamic> post(String path, [Object? body]) async => null;
}

class _FakeAuthState extends AuthState {
  _FakeAuthState(this._api);
  final ApiClient _api;
  @override
  ApiClient get api => _api;
}

Future<void> _pump(WidgetTester tester, List<Map<String, dynamic>> devices) async {
  SharedPreferences.setMockInitialValues({
    'dongle_wifi_enabled': true,
    'dongle_wifi_ssid': 'Home',
    'dongle_device_id': 'dev-1',
    'dongle_device_name': 'Tripper',
    'dongle_vehicle_id': 'v9',
  });
  FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform({
    'dongle_wifi_pass': 'wifi-secret',
    'dongle_api_key': 'abdev_old-account',
  });
  await tester.pumpWidget(
    ChangeNotifierProvider<AuthState>(
      create: (_) => _FakeAuthState(_FakeApi(devices)),
      child: const MaterialApp(home: DongleWifiScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => TestWidgetsFlutterBinding.ensureInitialized());

  testWidgets('push blocked when saved device id not in account list', (tester) async {
    await _pump(tester, [
      {
        'id': 'dev-2',
        'name': 'Tripper',
        'vehicle_id': 'v1',
        'last_seen_at': null,
        'created_at': '2026-08-16T10:00:00Z',
      }
    ]);

    expect(find.text('Push credentials'), findsNothing);
    expect(find.text('Link dongle'), findsOneWidget);
  });

  testWidgets('push available when saved device is in the account list', (tester) async {
    await _pump(tester, [
      {
        'id': 'dev-1',
        'name': 'Tripper',
        'vehicle_id': 'v9',
        'last_seen_at': null,
        'created_at': '2026-08-16T10:00:00Z',
      }
    ]);

    expect(find.text('Push credentials'), findsOneWidget);
  });
}
