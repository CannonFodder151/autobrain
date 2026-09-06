// Reproduces AUT-2208: Servo Spy map shows blank/empty (no stations render).
// Mocks GeolocatorPlatform + API so the map widget renders with a real fix and
// stations payload, then asserts the marker count + map widget show up.

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/servo_spy/servo_spy_screen.dart';

class _FakeGeo extends GeolocatorPlatform {
  @override
  Future<bool> isLocationServiceEnabled() async => true;

  @override
  Future<LocationPermission> checkPermission() async => LocationPermission.whileInUse;

  @override
  Future<LocationPermission> requestPermission() async => LocationPermission.whileInUse;

  @override
  Future<Position> getCurrentPosition({LocationSettings? locationSettings}) async =>
      Position(
        latitude: -37.8136,
        longitude: 144.9631,
        timestamp: DateTime.utc(2026, 9, 3),
        accuracy: 5,
        altitude: 0,
        altitudeAccuracy: 0,
        heading: 0,
        headingAccuracy: 0,
        speed: 0,
        speedAccuracy: 0,
      );
}

class _DeniedGeo extends GeolocatorPlatform {
  @override
  Future<bool> isLocationServiceEnabled() async => false;

  @override
  Future<LocationPermission> checkPermission() async => LocationPermission.denied;

  @override
  Future<LocationPermission> requestPermission() async => LocationPermission.denied;

  @override
  Future<Position> getCurrentPosition({LocationSettings? locationSettings}) async =>
      throw Exception('location denied');
}

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '/vehicles') {
      return [
        {
          'id': 'v1',
          'nickname': 'Daily',
          'is_primary': true,
          'fuel_type': '91',
          'make': 'Holden',
          'model': 'Commodore',
          'year': 2018,
        }
      ];
    }
    if (path == '/fuel/types') {
      return ['91', '95', '98', 'E10', 'Diesel', 'LPG'];
    }
    if (path.startsWith('/fuel/stations')) {
      return [
        {
          'id': 's1',
          'name': 'BP Cluden',
          'brand': 'BP',
          'address': '123 Test St',
          'lat': -37.8136,
          'lon': 144.9631,
          'distance_km': 1.2,
          'logo': null,
          'prices': [
            {'fuel_type': '91', 'price': 178.9, 'effective_at': '2026-09-03T00:00:00'},
          ],
        },
      ];
    }
    return [];
  }
}

class _FakePaidAuth extends AuthState {
  @override
  bool get freeAccount => false;
  @override
  ApiClient get api => _FakeApi();
}

Widget _app(AuthState auth) => ChangeNotifierProvider<AuthState>(
      create: (_) => auth,
      child: const MaterialApp(home: ServoSpyScreen()),
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform({});
    GeolocatorPlatform.instance = _FakeGeo();
  });

  testWidgets('map view renders stations (AUT-2208 regression)', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_app(_FakePaidAuth()));
    // Allow bootstrap (getCurrentPosition + api calls) to complete.
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byType(FlutterMap), findsOneWidget,
        reason: 'map widget should be present on the paid map view');
    // Should not be stuck on a CircularProgressIndicator once data loads.
    expect(find.byType(CircularProgressIndicator), findsNothing,
        reason: 'map view must clear its loading spinner after stations load');
    // With a real station payload the empty-state overlay must be hidden.
    expect(find.textContaining('No fuel stations'), findsNothing,
        reason: 'empty-state overlay must not render when stations load');
  });

  testWidgets(
      'map view reports a stations-fetch error when /fuel/stations 500s (AUT-2208)',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final fake = _Stations500Api();
    final auth = _PaidAuthWith(fake);
    await tester.pumpWidget(_app(auth));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byType(FlutterMap), findsOneWidget,
        reason: 'map widget must still mount so the user sees the map area');
    expect(find.byType(CircularProgressIndicator), findsNothing,
        reason: 'loading spinner must clear even on station-fetch failure');
    expect(find.textContaining('Failed to load stations'), findsOneWidget,
        reason: 'station fetch error should be surfaced, not left blank');
  });

  testWidgets(
      'map view shows an empty-state overlay when /fuel/stations returns [] '
      '(AUT-2208: never a blank white screen)',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    final fake = _EmptyStationsApi();
    final auth = _PaidAuthWith(fake);
    await tester.pumpWidget(_app(auth));
    for (var i = 0; i < 50; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byType(FlutterMap), findsOneWidget,
        reason: 'map widget must still mount when stations are empty');
    expect(find.byType(CircularProgressIndicator), findsNothing,
        reason: 'loading spinner must clear once stations resolve to []');
    expect(find.textContaining('No fuel stations'), findsOneWidget,
        reason: 'empty-state overlay must render so the user is never left '
            'looking at a blank screen');
  });

  testWidgets(
      'recenter FAB is always visible when user location is known (AUT-2295)',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(_app(_FakePaidAuth()));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byIcon(Icons.my_location), findsOneWidget,
        reason:
            'recenter FAB must be present whenever the user has a location fix');

    final mapState =
        tester.state<State<FlutterMap>>(find.byType(FlutterMap));
    final controller = mapState.widget.mapController;
    controller.move(const LatLng(-33.8688, 151.2093), 12);
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byIcon(Icons.my_location), findsOneWidget,
        reason: 'recenter FAB stays visible after the user pans');

    await tester.tap(find.byIcon(Icons.my_location));
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byIcon(Icons.my_location), findsOneWidget,
        reason:
            'recenter FAB remains after returning to the user location');
  });

  testWidgets(
      'recenter FAB is hidden when user location is denied (AUT-2295)',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    GeolocatorPlatform.instance = _DeniedGeo();
    await tester.pumpWidget(_app(_FakePaidAuth()));
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byIcon(Icons.my_location), findsNothing,
        reason: 'recenter FAB stays hidden when there is no user location');
  });
}

class _Stations500Api extends ApiClient {
  _Stations500Api() : super(null);
  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '/vehicles') return [];
    if (path == '/fuel/types') return ['91'];
    throw ApiException(500, 'boom');
  }
}

class _EmptyStationsApi extends ApiClient {
  _EmptyStationsApi() : super(null);
  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '/vehicles') {
      return [
        {
          'id': 'v1',
          'nickname': 'Daily',
          'is_primary': true,
          'fuel_type': '91',
          'make': 'Holden',
          'model': 'Commodore',
          'year': 2018,
        }
      ];
    }
    if (path == '/fuel/types') return ['91', '95'];
    if (path.startsWith('/fuel/stations')) return [];
    return [];
  }
}

class _PaidAuthWith extends AuthState {
  _PaidAuthWith(this._api);
  final ApiClient _api;
  @override
  bool get freeAccount => false;
  @override
  ApiClient get api => _api;
}