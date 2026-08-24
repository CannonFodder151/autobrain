// Regression tests for AUT-963 F1: "Push credentials" must be blocked when the
// saved device id is not present in the current account's device list, so the
// app can never provision a dongle with a previous account's key.
//
// AUT-966 F1: the provisioning write must be gated on explicit user
// confirmation of the dongle's identity (name + remoteId), and the payload
// written ONLY to the confirmed device — never the first BLE scan match.

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/settings/dongle_wifi_screen.dart';
import 'package:autobrain/services/dongle/dongle_ble.dart';

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
  Future<dynamic> post(String path,
          [Object? body, Map<String, String>? headers]) async =>
      null;
}

class _FailingApi extends ApiClient {
  _FailingApi() : super(null);

  @override
  Future<dynamic> get(String path) async => throw Exception('boom');

  @override
  Future<dynamic> post(String path,
          [Object? body, Map<String, String>? headers]) async =>
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

  tearDown(() {
    DongleBle.scanOverride = null;
    DongleBle.provisionOverride = null;
  });

  const dev1 = {
    'id': 'dev-1',
    'name': 'Tripper',
    'vehicle_id': 'v9',
    'last_seen_at': null,
    'created_at': '2026-08-16T10:00:00Z',
  };

  testWidgets('push blocked when saved device id not in account list',
      (tester) async {
    await _pump(tester, [
      {
        'id': 'dev-2',
        'name': 'Tripper',
        'vehicle_id': 'v1',
        'last_seen_at': null,
        'created_at': '2026-08-16T10:00:00Z',
      }
    ]);

    expect(
        find.textContaining(RegExp('Push credentials|Sync now')), findsNothing);
    expect(find.text('Link dongle'), findsOneWidget);
  });

  testWidgets('push available when saved device is in the account list',
      (tester) async {
    await _pump(tester, [dev1]);

    expect(find.textContaining(RegExp('Push credentials|Sync now')),
        findsOneWidget);
  });

  testWidgets('device-list fetch failure surfaces server hint, not no-dongle',
      (tester) async {
    await _pumpWith(tester, _FailingApi());

    expect(find.text('Could not reach the server.'), findsOneWidget);
    expect(find.textContaining('No dongle linked yet'), findsNothing);
  });

  testWidgets(
      'SSID/pass fields cap length at firmware buffer sizes (AUT-968 F3)',
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

    final fields =
        tester.widgetList<TextField>(find.byType(TextField)).toList();
    expect(fields.length, greaterThanOrEqualTo(2));
    expect(fields[0].maxLength, 32); // ssid[33] on the dongle
    expect(fields[1].maxLength, 63); // pass[64] on the dongle
  });

  // Opens the confirm-dongle dialog. pumpAndSettle is unusable while the
  // busy spinner animates, so pump a bounded number of frames instead.
  Future<void> openConfirmDialog(WidgetTester tester) async {
    await tester.tap(find.textContaining('Sync now'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  }

  testWidgets(
      'AUT-966: provisioning does NOT write without explicit device confirmation',
      (tester) async {
    final writes = <String>[];
    DongleBle.scanOverride = () async => const [
          DonglePeripheral(
              deviceId: 'AA:BB:CC:DD:EE:FF', name: 'AutoBrain-Tripper'),
        ];
    DongleBle.provisionOverride = (payload, deviceId) async {
      writes.add(deviceId);
      return 'ok';
    };

    await _pump(tester, [dev1]);
    await openConfirmDialog(tester);

    // Dialog surfaces the discovered identity (name + MAC/remoteId).
    expect(find.text('Confirm dongle'), findsOneWidget);
    expect(find.text('AA:BB:CC:DD:EE:FF'), findsOneWidget);
    expect(find.text('AutoBrain-Tripper'), findsWidgets);

    // Cancel → nothing written to any device. The status line sits below the
    // ListView fold, so find it in the built (offstage) subtree too.
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(writes, isEmpty);
    expect(find.text('Provisioning cancelled.', skipOffstage: false),
        findsOneWidget);
  });

  testWidgets(
      'AUT-966: payload written only to the user-confirmed device, not the '
      'first scan match', (tester) async {
    final writes = <String>[];
    // First match is a spoof; the real dongle is second.
    DongleBle.scanOverride = () async => const [
          DonglePeripheral(deviceId: 'AA:SPOOF', name: 'AutoBrain-Tripper'),
          DonglePeripheral(deviceId: 'BB:REAL', name: 'AutoBrain-Tripper 2'),
        ];
    DongleBle.provisionOverride = (payload, deviceId) async {
      writes.add(deviceId);
      return 'ok';
    };

    await _pump(tester, [dev1]);
    await openConfirmDialog(tester);

    // Both matches offered; neither is auto-picked.
    expect(find.text('AA:SPOOF'), findsOneWidget);
    expect(find.text('BB:REAL'), findsOneWidget);
    expect(writes, isEmpty);

    // User confirms the second device → only that id receives the write.
    await tester.tap(find.text('AutoBrain-Tripper 2'));
    await tester.pumpAndSettle();

    expect(writes, ['BB:REAL']);
    expect(find.textContaining('Dongle provisioned', skipOffstage: false),
        findsOneWidget);
  });

  testWidgets(
      'AUT-966: payload written to the confirmed device even when it '
      'is the only match', (tester) async {
    final writes = <String>[];
    DongleBle.scanOverride = () async => const [
          DonglePeripheral(deviceId: 'CC:ONLY', name: 'AutoBrain-Tripper'),
        ];
    DongleBle.provisionOverride = (payload, deviceId) async {
      writes.add(deviceId);
      return 'ok';
    };

    await _pump(tester, [dev1]);
    await openConfirmDialog(tester);

    expect(writes, isEmpty, reason: 'still requires explicit confirmation');

    await tester.tap(find.text('AutoBrain-Tripper'));
    await tester.pumpAndSettle();

    expect(writes, ['CC:ONLY']);
  });
}
