// Tests for the native GPS helper (AUT-539): the permission/service gates and
// coordinate mapping, driven by a fake GeolocatorPlatform. Pure Dart, no channels.

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
      throw Exception('no fix within time limit');
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
    final pos = await getCurrentPosition();
    expect(pos, {'latitude': -37.8136, 'longitude': 144.9631});
  });

  test('requests permission once when previously denied', () async {
    geo.permission = LocationPermission.denied;
    final pos = await getCurrentPosition();
    expect(geo.permissionRequests, 1);
    expect(pos, {'latitude': -37.8136, 'longitude': 144.9631});
  });

  test('returns null when location services are off', () async {
    geo.serviceEnabled = false;
    expect(await getCurrentPosition(), isNull);
    expect(geo.permissionRequests, 0);
  });

  test('returns null when permission is denied after request', () async {
    geo.permission = LocationPermission.deniedForever;
    expect(await getCurrentPosition(), isNull);
  });

  test('returns null when no fix arrives in time', () async {
    geo.failFix = true;
    expect(await getCurrentPosition(), isNull);
  });
}
