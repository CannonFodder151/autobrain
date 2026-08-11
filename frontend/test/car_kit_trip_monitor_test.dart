// Tests for the phone-side auto trip path (AUT-367): the deterministic
// car-kit BT connection + GPS speed-guard state machine that drives the shared
// ObdTripRecorder. Pure Dart, no platform channels.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/services/car/car_kit_trip_monitor.dart';
import 'package:autobrain/services/obd/obd_trip_recorder.dart';

class _MemStore implements TripStore {
  final Map<String, String> _data = {};

  @override
  Future<String?> read(String key) async => _data[key];

  @override
  Future<void> write(String key, String value) async {
    _data[key] = value;
  }
}

class _Recorder {
  _Recorder() {
    writes = [];
    recorder = ObdTripRecorder(
      store: _MemStore(),
      writeTrip: (trip) async => writes.add(trip),
      now: () => DateTime.utc(2026, 8, 11, 10, 0, 0),
    );
    recorder.bind('v1');
  }

  late ObdTripRecorder recorder;
  late List<PendingTrip> writes;
}

class _Clock {
  DateTime t = DateTime.utc(2026, 8, 11, 10, 0, 0);
  DateTime now() => t;
  void advance(Duration d) => t = t.add(d);
}

CarKitTripMonitor _build(_Recorder r, _Clock clock,
    {bool enabled = true}) {
  final m = CarKitTripMonitor(
    recorder: r.recorder,
    now: clock.now,
  );
  m.enabled = enabled;
  return m;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('speed guard', () {
    test('no trip until the link is up AND speed is sustained', () async {
      final r = _Recorder();
      final clock = _Clock();
      final m = _build(r, clock);
      // Speed alone, no car-kit link: no trip.
      await m.feedSpeed(60);
      expect(m.isTripActive, isFalse);
      // Link up but not moving: no trip.
      await m.feedConnection(CarKitLinkState.connected);
      await m.feedSpeed(3);
      expect(m.isTripActive, isFalse);
      // Moving but below the sustained window (commitSeconds=5): no trip.
      clock.advance(const Duration(seconds: 1));
      await m.feedSpeed(60);
      clock.advance(const Duration(seconds: 3));
      await m.feedSpeed(60);
      expect(m.isTripActive, isFalse);
      // Sustained for the full window: trip commits.
      clock.advance(const Duration(seconds: 2));
      await m.feedSpeed(60);
      expect(m.isTripActive, isTrue);
      m.dispose();
    });

    test('a passenger (no car-kit link) never starts a trip', () async {
      final r = _Recorder();
      final clock = _Clock();
      final m = _build(r, clock);
      for (var i = 0; i < 20; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(60);
      }
      expect(m.isTripActive, isFalse);
      expect(r.writes, isEmpty);
      m.dispose();
    });

    test('enabled=false ignores the whole path', () async {
      final r = _Recorder();
      final clock = _Clock();
      final m = _build(r, clock, enabled: false);
      await m.feedConnection(CarKitLinkState.connected);
      for (var i = 0; i < 10; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(60);
      }
      expect(m.isTripActive, isFalse);
      m.dispose();
    });
  });

  group('stop', () {
    test('link drop closes the trip immediately', () async {
      final r = _Recorder();
      final clock = _Clock();
      final m = _build(r, clock);
      await m.feedConnection(CarKitLinkState.connected);
      for (var i = 0; i < 6; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(60);
      }
      expect(m.isTripActive, isTrue);
      await m.feedConnection(CarKitLinkState.disconnected);
      expect(m.isTripActive, isFalse);
      expect(r.writes, hasLength(1));
      expect(r.writes.first.source, 'car_auto');
      m.dispose();
    });

    test('sustained low speed while linked closes the trip', () async {
      final r = _Recorder();
      final clock = _Clock();
      final m = _build(r, clock);
      await m.feedConnection(CarKitLinkState.connected);
      for (var i = 0; i < 6; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(60);
      }
      expect(m.isTripActive, isTrue);
      // Parked: below stopSpeedKmh (5) for stopSeconds (20).
      for (var i = 0; i < 21; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(0);
      }
      expect(m.isTripActive, isFalse);
      expect(r.writes, hasLength(1));
      m.dispose();
    });

    test('distance is accumulated from GPS speed (odometer diff)', () async {
      final r = _Recorder();
      final clock = _Clock();
      final m = _build(r, clock);
      await m.feedConnection(CarKitLinkState.connected);
      for (var i = 0; i < 6; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(60);
      }
      // 60 km/h for 3600 s = 60 km.
      for (var i = 0; i < 3600; i++) {
        clock.advance(const Duration(seconds: 1));
        await m.feedSpeed(60);
      }
      await m.feedConnection(CarKitLinkState.disconnected);
      await r.recorder.flush();
      expect(r.writes, hasLength(1));
      final d = r.writes.first.distanceKm;
      expect(d, isNotNull);
      expect(d!, closeTo(60, 1));
      m.dispose();
    });
  });
}
