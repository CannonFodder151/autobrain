/// Tests for the native GPS helper (AUT-539, AUT-4489): the permission/service
/// gates and coordinate mapping, driven by a fake GeolocatorPlatform.
/// Returns a typed [LocationResult] instead of a nullable map so callers can
/// distinguish "services off" from "permission denied" from "timeout".
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';

import 'package:autobrain/core/geoloc_io.dart';

class _FakeGeo extends GeolocatorPlatform {
  bool serviceEnabled = true;
  LocationPermission permission = LocationPermission.whileInUse;
  int permissionRequests = 0;
  bool failFix = false;

  @override
  Future<bool> isLocationServiceEnabled() async => serviceEnabled;

  @override
  Future<LocationPermission> checkPermission() async => permission;

  @override
  Future<LocationPermission> requestPermission() async {
    permissionRequests++;
    permission = LocationPermission.whileInUse;
    return permission;
  }

  @override
  Future<Position> getCurrentPosition({LocationSettings? locationSettings}) {
    if (failFix) {
      throw TimeoutException('no fix within time limit', 'geolocator');
    }
    return Future.value(Position(
      latitude: -37.8136,
      longitude: 144.9631,
      timestamp: DateTime.utc(2026, 8, 13),
      accuracy: 5,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    ));
  }
}

void main() {
  late _FakeGeo geo;
  setUp(() {
    geo = _FakeGeo();
    GeolocatorPlatform.instance = geo;
  });

  test('returns coordinates when service, permission and fix are OK', () async {
    final result = await getCurrentPosition();
    expect(result.isSuccess, isTrue);
    expect(result.coordinates, {'latitude': -37.8136, 'longitude': 144.9631});
  });

  test('requests permission once when previously denied', () async {
    geo.permission = LocationPermission.denied;
    final result = await getCurrentPosition();
    expect(geo.permissionRequests, 1);
    expect(result.isSuccess, isTrue);
  });

  test('returns serviceDisabled when location services are off', () async {
    geo.serviceEnabled = false;
    final result = await getCurrentPosition();
    expect(result, isA<LocationResult>());
    expect(result.errorMessage, contains('Location services are turned off'));
    expect(geo.permissionRequests, 0);
  });

  test('returns permissionDeniedForever when permanently denied', () async {
    geo.permission = LocationPermission.deniedForever;
    final result = await getCurrentPosition();
    expect(result.errorMessage, contains('permanently denied'));
    expect(result.canOpenSettings, isTrue);
  });

  test('returns timeout when no fix arrives in time', () async {
    geo.failFix = true;
    final result = await getCurrentPosition();
    expect(result.errorMessage, contains('GPS fix in time'));
  });
}