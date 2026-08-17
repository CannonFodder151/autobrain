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

class _FailingApi extends ApiClient {
  _FailingApi() : super(null);

  @override
  Future<dynamic> get(String path) async => throw Exception('boom');

  @override
  Future<dynamic> post(String path, [Object? body]) async =>
      throw Exception('boom');
}

class _FakeAuthState extends AuthState {
  _FakeAuthState(this._api);
  final ApiClient _api;
  @override
  ApiClient get api => _api;
}

Future<void> _pump(WidgetTester tester, List<Map<String, dynamic>> devices) =>
    _pumpWith(tester, _FakeApi(devices));

Future<void> _pumpWith(WidgetTester tester, ApiClient api) async {
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
      create: (_) => _FakeAuthState(api),
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

  testWidgets('device-list fetch failure surfaces server hint, not no-dongle',
      (tester) async {
    await _pumpWith(tester, _FailingApi());

    expect(find.text('Could not reach the server.'), findsOneWidget);
    expect(find.textContaining('No dongle linked yet'), findsNothing);
  });

  testWidgets('SSID/pass fields cap length at firmware buffer sizes (AUT-968 F3)',
      (tester) async {
    await _pump(tester, [
      {
        'id': 'dev-1',
        'name': 'Tripper',
        'vehicle_id': 'v9',
        'last_seen_at': null,
        'created_at': '2026-08-16T10:00:00Z',
      }
    ]);

    final fields = tester.widgetList<TextField>(find.byType(TextField)).toList();
    expect(fields.length, greaterThanOrEqualTo(2));
    expect(fields[0].maxLength, 32); // ssid[33] on the dongle
    expect(fields[1].maxLength, 63); // pass[64] on the dongle
  });
}
