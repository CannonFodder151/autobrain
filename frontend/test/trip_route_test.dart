import 'package:autobrain/core/models.dart';
import 'package:autobrain/core/trip_route.dart';
import 'package:flutter_test/flutter_test.dart';

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
}
