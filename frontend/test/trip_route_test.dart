import 'package:autobrain/core/models.dart';
import 'package:autobrain/core/trip_route.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

void main() {
  test('validRoute drops 0,0 no-fix and out-of-range samples', () {
    final samples = [
      const GpsPoint(1, 0, 0), // no fix
      const GpsPoint(2, -37.6385, 145.1936),
      const GpsPoint(3, -91, 145.0), // out of range
      const GpsPoint(4, -37.6386, 145.1937),
    ];
    final route = validRoute(samples);
    expect(route.length, 2);
    expect(route.first.latitude, -37.6385);
    expect(hasRoute(samples), isTrue);
  });

  test('validRoute dedupes consecutive identical fixes', () {
    final samples = [
      const GpsPoint(1, -37.6, 145.1),
      const GpsPoint(2, -37.6, 145.1), // duplicate
      const GpsPoint(3, -37.6, 145.2),
    ];
    expect(validRoute(samples).length, 2);
  });

  test('hasRoute is false without 2 valid points', () {
    expect(hasRoute(const [GpsPoint(1, 0, 0)]), isFalse);
    expect(hasRoute(const []), isFalse);
    expect(hasRoute(const [GpsPoint(1, -37.6, 145.1)]), isFalse);
  });

  test('LogEntry.fromJson parses gps_samples', () {
    final e = LogEntry.fromJson({
      'id': 'x',
      'started_at': '2026-08-12T10:00:00Z',
      'gps_samples': [
        {'t': 1723400000, 'lat': -37.6, 'lng': 145.1},
        {'t': 1723400001, 'lat': -37.7, 'lng': 145.2},
      ],
    });
    expect(e.gpsSamples.length, 2);
    expect(e.gpsSamples.first.lat, -37.6);
    expect(e.hasRoute, isTrue);
  });

  group('googleMapsRouteUrl', () {
    test('single point falls back to a q= URL', () {
      final url = googleMapsRouteUrl(const [LatLng(-37.6, 145.1)]);
      expect(url, contains('www.google.com/maps?q=-37.600000,145.100000'));
    });

    test('two points build a path= URL with both endpoints', () {
      final url = googleMapsRouteUrl(const [
        LatLng(-37.6385, 145.1936),
        LatLng(-37.6387, 145.1939),
      ]);
      expect(url, startsWith('https://www.google.com/maps?path='));
      expect(url, contains('-37.638500,145.193600'));
      expect(url, contains('-37.638700,145.193900'));
    });

    test('long routes are downsampled to googleMapsMaxPathPoints', () {
      final route = List.generate(
        2000,
        (i) => LatLng(-37.6 + i * 1e-5, 145.1 + i * 1e-5),
      );
      final url = googleMapsRouteUrl(route);
      final path = url.substring(url.indexOf('weight:4|') + 'weight:4|'.length);
      final pointCount = '|'.allMatches(path).length + 1;
      expect(pointCount, googleMapsMaxPathPoints);
      expect(url, contains('-37.600000,145.100000'));
      expect(url, contains('-37.580010,145.119990'));
    });

    test('empty route falls back to bare maps URL', () {
      expect(googleMapsRouteUrl(const []), 'https://www.google.com/maps');
    });
  });
}
