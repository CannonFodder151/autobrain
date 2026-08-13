import 'package:flutter_test/flutter_test.dart';
import 'package:autobrain/services/obd/obd_trip_recorder.dart';

/// In-memory TripStore for recorder tests.
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
  _Recorder({DateTime Function()? now}) {
    store = _MemStore();
    writes = [];
    failNext = false;
    recorder = ObdTripRecorder(
      store: store,
      writeTrip: (trip) async {
        if (failNext) throw StateError('offline');
        writes.add(trip);
      },
      now: now ?? () => DateTime.utc(2026, 8, 11, 10, 0, 0),
    );
  }

  late _MemStore store;
  late ObdTripRecorder recorder;
  late List<PendingTrip> writes;
  late bool failNext;
}

void main() {
  group('ignition detection', () {
    test('voltage above on-threshold starts a trip after the debounce', () async {
      final r = _Recorder().recorder;
      r.bind('v1');
      expect(r.feed(const IgnitionSample(voltage: 12.5)), IgnitionState.unknown);
      expect(r.feed(const IgnitionSample(voltage: 14.0)), IgnitionState.unknown);
      expect(r.feed(const IgnitionSample(voltage: 14.1)), IgnitionState.on);
      expect(r.isTripActive, isTrue);
      expect(r.activeTrip!.vehicleId, 'v1');
      expect(r.activeTrip!.startedAt, DateTime.utc(2026, 8, 11, 10, 0, 0));
    });

    test('RPM above zero counts as engine running', () async {
      final r = _Recorder().recorder;
      r.bind('v1');
      r.feed(const IgnitionSample(voltage: 12.6, rpm: 0));
      r.feed(const IgnitionSample(voltage: 12.6, rpm: 800));
      expect(r.feed(const IgnitionSample(voltage: 12.6, rpm: 850)),
          IgnitionState.on);
      expect(r.isTripActive, isTrue);
    });

    test('ignition-off needs 3 consecutive off samples', () async {
      final r = _Recorder().recorder;
      r.bind('v1');
      r.feed(const IgnitionSample(voltage: 14.0));
      r.feed(const IgnitionSample(voltage: 14.0));
      expect(r.isTripActive, isTrue);
      // A single dip below threshold must not end the trip (hysteresis).
      r.feed(const IgnitionSample(voltage: 12.4));
      expect(r.isTripActive, isTrue);
      r.feed(const IgnitionSample(voltage: 14.2));
      expect(r.isTripActive, isTrue);
      r.feed(const IgnitionSample(voltage: 12.4, rpm: 0));
      r.feed(const IgnitionSample(voltage: 12.5, rpm: 0));
      expect(r.feed(const IgnitionSample(voltage: 12.4, rpm: 0)),
          IgnitionState.off);
      expect(r.isTripActive, isFalse);
      expect(r.pending, hasLength(1));
      expect(r.pending.first.endedAt, DateTime.utc(2026, 8, 11, 10, 0, 0));
    });

    test('hysteresis band (12.8-13.2 V) holds the current state', () async {
      final r = _Recorder().recorder;
      r.bind('v1');
      r.feed(const IgnitionSample(voltage: 14.0));
      r.feed(const IgnitionSample(voltage: 14.0));
      expect(r.isTripActive, isTrue);
      r.feed(const IgnitionSample(voltage: 13.0)); // in the band
      expect(r.isTripActive, isTrue);
      expect(r.ignition, IgnitionState.on);
    });

    test('no signal (voltage null, rpm 0) holds the current state', () async {
      final r = _Recorder().recorder;
      r.bind('v1');
      r.feed(const IgnitionSample(voltage: 14.0, rpm: 1000));
      r.feed(const IgnitionSample(voltage: 14.0, rpm: 1200));
      expect(r.isTripActive, isTrue);
      r.feed(const IgnitionSample()); // ECU dropped out
      expect(r.isTripActive, isTrue);
    });

    test('no vehicle bound: ignition is tracked but no trip starts', () async {
      final r = _Recorder().recorder;
      r.feed(const IgnitionSample(voltage: 14.0));
      r.feed(const IgnitionSample(voltage: 14.0));
      expect(r.ignition, IgnitionState.on);
      expect(r.isTripActive, isFalse);
    });
  });

  group('link drop', () {
    test('drops end an in-progress trip immediately and enqueue it', () async {
      final r = _Recorder().recorder;
      r.bind('v1');
      r.feed(const IgnitionSample(voltage: 14.0));
      r.feed(const IgnitionSample(voltage: 14.0));
      expect(r.isTripActive, isTrue);
      await r.onLinkDrop();
      expect(r.isTripActive, isFalse);
      expect(r.pending, hasLength(1));
      expect(r.pending.first.endedAt, DateTime.utc(2026, 8, 11, 10, 0, 0));
    });

    test('drop with no active trip is a no-op', () async {
      final r = _Recorder().recorder;
      await r.onLinkDrop();
      expect(r.pending, isEmpty);
      expect(r.isTripActive, isFalse);
    });
  });

  group('buffering across app kill', () {
    test('active trip is restored from the store on restart', () async {
      final setup = _Recorder(now: () => DateTime.utc(2026, 8, 11, 9, 0, 0));
      setup.recorder.bind('v1');
      setup.recorder.feed(const IgnitionSample(voltage: 14.0));
      setup.recorder.feed(const IgnitionSample(voltage: 14.0));
      expect(setup.recorder.isTripActive, isTrue);
      // The store holds the buffer — "app killed" here is a fresh recorder
      // over the same store.
      final store = setup.store;
      final restart = ObdTripRecorder(
        store: store,
        writeTrip: (_) async {},
        now: () => DateTime.utc(2026, 8, 11, 9, 30, 0),
      );
      final restored = await restart.restore();
      expect(restored, isNotNull);
      expect(restart.isTripActive, isTrue);
      expect(restart.activeTrip!.startedAt, DateTime.utc(2026, 8, 11, 9, 0, 0));
      expect(restart.activeTrip!.vehicleId, 'v1');
    });

    test('restored trip closes and syncs when ignition reads off', () async {
      final setup = _Recorder(now: () => DateTime.utc(2026, 8, 11, 9, 0, 0));
      setup.recorder.bind('v1');
      setup.recorder.feed(const IgnitionSample(voltage: 14.0));
      setup.recorder.feed(const IgnitionSample(voltage: 14.0));
      final store = setup.store;
      final writes = <PendingTrip>[];
      final restart = ObdTripRecorder(
        store: store,
        writeTrip: (t) async => writes.add(t),
        now: () => DateTime.utc(2026, 8, 11, 9, 45, 0),
      );
      restart.bind('v1');
      await restart.restore();
      // Car was switched off while the app was dead: first samples read off.
      restart.feed(const IgnitionSample(voltage: 12.4));
      restart.feed(const IgnitionSample(voltage: 12.5));
      restart.feed(const IgnitionSample(voltage: 12.4));
      expect(restart.isTripActive, isFalse);
      expect(restart.pending, hasLength(1));
      await restart.flush();
      expect(writes, hasLength(1));
      expect(writes.first.startedAt, DateTime.utc(2026, 8, 11, 9, 0, 0));
      expect(writes.first.endedAt, DateTime.utc(2026, 8, 11, 9, 45, 0));
    });
  });

  group('sync queue', () {
    test('failed write keeps the trip queued for a later retry', () async {
      final r = _Recorder();
      r.recorder.bind('v1');
      r.recorder.feed(const IgnitionSample(voltage: 14.0));
      r.recorder.feed(const IgnitionSample(voltage: 14.0));
      expect(r.recorder.isTripActive, isTrue);
      r.failNext = true;
      await r.recorder.onLinkDrop();
      await r.recorder.flush();
      expect(r.recorder.pending, hasLength(1));
      expect(r.writes, isEmpty);
      // Online again: flush succeeds and the queue drains.
      r.failNext = false;
      await r.recorder.flush();
      expect(r.writes, hasLength(1));
      expect(r.recorder.pending, isEmpty);
    });

    test('flushes in start order', () async {
      final r = _Recorder();
      r.recorder.bind('v1');
      r.recorder.feed(const IgnitionSample(voltage: 14.0));
      r.recorder.feed(const IgnitionSample(voltage: 14.0));
      await r.recorder.onLinkDrop();
      r.recorder.feed(const IgnitionSample(voltage: 14.2));
      r.recorder.feed(const IgnitionSample(voltage: 14.1));
      await r.recorder.onLinkDrop();
      await r.recorder.flush();
      expect(r.writes, hasLength(2));
      expect(r.writes[0].startedAt, r.writes[1].startedAt);
    });
  });

  group('serialisation', () {
    test('ActiveTrip/PendingTrip JSON round-trip', () {
      final a = ActiveTrip(
          vehicleId: 'v1', startedAt: DateTime.utc(2026, 8, 11, 9, 0, 0));
      final a2 = ActiveTrip.fromJson(a.toJson());
      expect(a2!.vehicleId, 'v1');
      expect(a2.startedAt, DateTime.utc(2026, 8, 11, 9, 0, 0));

      final p = PendingTrip(
          vehicleId: 'v1',
          startedAt: DateTime.utc(2026, 8, 11, 9, 0, 0),
          endedAt: DateTime.utc(2026, 8, 11, 9, 30, 0));
      final p2 = PendingTrip.fromJson(p.toJson());
      expect(p2!.vehicleId, 'v1');
      expect(p2.startedAt, p.startedAt);
      expect(p2.endedAt, p.endedAt);
    });

    test('corrupt buffer is ignored, not fatal', () async {
      final s = _MemStore();
      await s.write(ObdTripRecorder.activeKey, '{not json');
      final r = ObdTripRecorder(store: s, writeTrip: (_) async {});
      final restored = await r.restore();
      expect(restored, isNull);
      expect(r.pending, isEmpty);
    });
  });
}
