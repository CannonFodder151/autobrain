/// Automatic OBD trip recording (GoFar-style): start/stop logbook trips from
/// ignition signals with no user interaction.
///
/// Pure Dart with zero Flutter/BT imports so it unit-tests without hardware:
/// the caller ([ObdTripMonitor]) feeds polled [IgnitionSample]s (battery
/// voltage Mode 01 PID `0142`, engine RPM `010C`, BT link state). The recorder
/// decides ignition on/off with hysteresis + debounce, keeps the in-progress
/// trip in a persistent buffer (so a mid-drive app kill does not lose it) and
/// queues finished trips for a retrying backend sync.
///
/// Signal model (validated against VGate iCar Pro behaviour):
///   engine running ≈ 13.8-14.4 V, ignition off ≈ 12.5 V, and the adapter
///   sleeps + drops the BT link shortly after ignition-off.
library;

import 'dart:async';
import 'dart:convert';

/// One polled signal set used to judge ignition state.
class IgnitionSample {
  const IgnitionSample({this.voltage, this.rpm});

  /// Battery voltage in volts (`0142`); null when the ECU does not report it.
  final double? voltage;

  /// Engine RPM (`010C`); 0 when the engine is off.
  final double? rpm;
}

enum IgnitionState { unknown, off, on }

/// The shared "car connected" abstraction. Both auto-trip trigger paths emit
/// this into the same recorder (the auto start/stop service):
///  - OBD/VGate dongle path (AUT-362): ignition voltage/RPM → connected/disconnected
///  - Phone/car-kit path (AUT-367): head-unit BT link + GPS speed guard
///    (see [CarKitTripMonitor]) → connected/disconnected
enum CarConnectionState { disconnected, connected }

/// An in-progress trip kept in the local buffer.
class ActiveTrip {
  const ActiveTrip({
    required this.vehicleId,
    required this.startedAt,
    this.source = 'obd_auto',
    this.gpsSamples = const [],
  });

  final String vehicleId;
  final DateTime startedAt;
  final String source;

  /// Trip route fixes `{"t": epoch, "lat": deg, "lng": deg}` (AUT-395),
  /// accumulated while the drive is active and persisted so an app kill
  /// mid-drive does not lose the route.
  final List<Map<String, dynamic>> gpsSamples;

  Map<String, dynamic> toJson() => {
        'vehicleId': vehicleId,
        'startedAt': startedAt.toIso8601String(),
        'source': source,
        'gpsSamples': gpsSamples,
      };

  static ActiveTrip? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    final started = DateTime.tryParse(j['startedAt'] as String? ?? '');
    final vehicleId = j['vehicleId'] as String?;
    if (vehicleId == null || started == null) return null;
    return ActiveTrip(
        vehicleId: vehicleId,
        startedAt: started,
        source: j['source'] as String? ?? 'obd_auto',
        gpsSamples: [
          for (final s in j['gpsSamples'] as List? ?? const [])
            if (s is Map<String, dynamic>) s
        ]);
  }
}

/// A finished trip queued for the backend logbook.
class PendingTrip {
  const PendingTrip({
    required this.vehicleId,
    required this.startedAt,
    required this.endedAt,
    this.distanceKm,
    this.source = 'obd_auto',
    this.gpsSamples = const [],
  });

  final String vehicleId;
  final DateTime startedAt;
  final DateTime endedAt;

  /// Trip distance in km (GPS odometer diff on the phone path, null on the
  /// OBD path which has no odometer).
  final double? distanceKm;

  /// Backend `source` tag: `obd_auto` (VGate dongle, AUT-362) or `car_auto`
  /// (phone car-kit path, AUT-367).
  final String source;

  /// Trip route fixes carried to the backend (AUT-395).
  final List<Map<String, dynamic>> gpsSamples;

  Map<String, dynamic> toJson() => {
        'vehicleId': vehicleId,
        'startedAt': startedAt.toIso8601String(),
        'endedAt': endedAt.toIso8601String(),
        if (distanceKm != null) 'distanceKm': distanceKm,
        'source': source,
        'gpsSamples': gpsSamples,
      };

  static PendingTrip? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    final started = DateTime.tryParse(j['startedAt'] as String? ?? '');
    final ended = DateTime.tryParse(j['endedAt'] as String? ?? '');
    final vehicleId = j['vehicleId'] as String?;
    if (vehicleId == null || started == null || ended == null) return null;
    return PendingTrip(
      vehicleId: vehicleId,
      startedAt: started,
      endedAt: ended,
      distanceKm: (j['distanceKm'] as num?)?.toDouble(),
      source: j['source'] as String? ?? 'obd_auto',
      gpsSamples: [
        for (final s in j['gpsSamples'] as List? ?? const [])
          if (s is Map<String, dynamic>) s
      ],
    );
  }
}

/// Persistent key-value store (SharedPreferences-backed in the app). Two keys
/// survive app kills: the active-trip buffer and the pending-sync queue.
abstract class TripStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
}

/// Writes one finished trip to the backend logbook. Throws on failure so the
/// recorder keeps it queued for a later retry.
typedef TripWriter = Future<void> Function(PendingTrip trip);

class ObdTripRecorder {
  ObdTripRecorder({
    required this.store,
    required this.writeTrip,
    DateTime Function()? now,
  }) : now = now ?? DateTime.now;

  final TripStore store;
  final TripWriter writeTrip;
  final DateTime Function() now;

  static const activeKey = 'obd.trip.active.v1';
  static const pendingKey = 'obd.trip.pending.v1';

  // Ignition thresholds (VGate iCar Pro): running ≈ 13.8-14.4 V, off ≈ 12.5 V.
  static const double onVoltage = 13.2;
  static const double offVoltage = 12.8;
  static const int onDebounce = 2; // consecutive on-samples (~4s at 2s poll)
  static const int offDebounce = 3; // consecutive off-samples (~6s)

  /// Max route fixes kept per trip (~1 fix/s → 40 min of driving).
  static const int maxGpsSamples = 2400;

  /// Persist the growing route buffer to the store at most this often (a write
  /// per fix would thrash SharedPreferences and be O(n²) over a long drive);
  /// the trip end always flushes. Bounds app-kill route loss to ~5s of fixes.
  static const Duration gpsPersistInterval = Duration(seconds: 5);

  IgnitionState _ignition = IgnitionState.unknown;
  int _onCount = 0;
  int _offCount = 0;

  String? _vehicleId;
  ActiveTrip? _active;
  List<PendingTrip> _pending = const [];
  bool _flushing = false;
  DateTime? _lastGpsPersist;

  IgnitionState get ignition => _ignition;
  ActiveTrip? get activeTrip => _active;
  bool get isTripActive => _active != null;
  List<PendingTrip> get pending => List.unmodifiable(_pending);

  /// Binds the vehicle whose logbook auto-trips land in. Called by the monitor
  /// when a vehicle is selected; a resumed buffered trip keeps ITS vehicle.
  void bind(String vehicleId) => _vehicleId = vehicleId;

  /// Restores buffered state after an app start/kill. Returns the active trip
  /// that survived (if any) so the caller can keep recording or close it. A
  /// restored trip is treated as ignition-on — the first off samples close it.
  Future<ActiveTrip?> restore() async {
    _active = await _readActive();
    _pending = await _readPending();
    if (_active != null) _ignition = IgnitionState.on;
    return _active;
  }

  Future<ActiveTrip?> _readActive() async {
    final raw = await store.read(activeKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      return ActiveTrip.fromJson(jsonDecode(raw) as Map<String, dynamic>?);
    } catch (_) {
      return null;
    }
  }

  Future<List<PendingTrip>> _readPending() async {
    final raw = await store.read(pendingKey);
    if (raw == null || raw.isEmpty) return const [];
    try {
      return (jsonDecode(raw) as List)
          .map((e) => PendingTrip.fromJson(e as Map<String, dynamic>?))
          .whereType<PendingTrip>()
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<void> _writeActive() async {
    await store.write(
        activeKey, _active == null ? '' : jsonEncode(_active!.toJson()));
  }

  Future<void> _writePending() async {
    await store.write(pendingKey, jsonEncode([for (final p in _pending) p.toJson()]));
  }

  /// Feeds one polled signal set; updates ignition state and trip lifecycle.
  /// Callers should also call [onLinkDrop] when the BT session ends.
  IgnitionState feed(IgnitionSample sample) {
    switch (_intent(sample)) {
      case IgnitionState.on:
        _onCount++;
        _offCount = 0;
      case IgnitionState.off:
        _offCount++;
        _onCount = 0;
      case IgnitionState.unknown:
        break; // hysteresis band / no signal: hold the current state
    }

    if (_onCount >= onDebounce && _ignition != IgnitionState.on) {
      _onCount = 0;
      _offCount = 0;
      _ignition = IgnitionState.on;
      unawaited(_startTrip());
    } else if (_offCount >= offDebounce && _ignition == IgnitionState.on) {
      _onCount = 0;
      _offCount = 0;
      _ignition = IgnitionState.off;
      unawaited(_endTrip());
    }
    return _ignition;
  }

  /// The BT link dropped (adapter sleeping after ignition-off, or an error).
  /// We can no longer sample signals, so close any in-progress trip now.
  Future<void> onLinkDrop() async {
    if (_active == null) return;
    _ignition = IgnitionState.off;
    _onCount = 0;
    _offCount = 0;
    await _endTrip();
  }

  /// Shared "car connected" feed — both auto-trip trigger paths converge here.
  ///
  /// The phone/car-kit path (AUT-367) feeds this with the outcome of its BT
  /// connection + GPS speed guard; the OBD path (AUT-362) reaches the same
  /// start/stop lifecycle through [feed] and [onLinkDrop]. Connected starts a
  /// trip, disconnected closes it (with an optional GPS-odometer distance).
  ///
  /// The caller owns debounce/speed-guard policy; this is the plain start/stop
  /// seam so both triggers drive one recorder.
  Future<void> feedCarConnection(
    CarConnectionState state, {
    double? distanceKm,
    String source = 'obd_auto',
  }) async {
    switch (state) {
      case CarConnectionState.connected:
        await _startTrip(source: source);
      case CarConnectionState.disconnected:
        // Each trigger only closes the trip it started. Without this a car-kit
        // BT drop would close an OBD/VGate trip early and a later ACL flap
        // could open a second (car_auto) trip for the same drive (T5 double
        // trip). The OBD path closes its own trips via [feed]/[onLinkDrop].
        if (_active?.source != source) return;
        await _endTrip(distanceKm: distanceKm);
    }
  }

  IgnitionState _intent(IgnitionSample s) {
    if (s.rpm != null && s.rpm! > 0) return IgnitionState.on;
    final v = s.voltage;
    if (v == null) return IgnitionState.unknown;
    if (v >= onVoltage) return IgnitionState.on;
    if (v <= offVoltage) return IgnitionState.off;
    return IgnitionState.unknown; // 12.8-13.2 V band: hold
  }

  Future<void> _startTrip({String source = 'obd_auto'}) async {
    if (_active != null) return;
    if (_vehicleId == null) return; // nothing bound yet
    _lastGpsPersist = null;
    _active = ActiveTrip(
        vehicleId: _vehicleId!, startedAt: now(), source: source);
    await _writeActive();
  }

  /// Feeds one GPS fix (lat/lon, WGS84) recorded while a trip is active.
  /// Invalid `0,0` fixes (no lock) are dropped — deterministic, no AI. The
  /// route survives app kills via the persisted active-trip buffer and lands
  /// on the backend trip as `gps_samples`.
  void feedPosition(double lat, double lng) {
    final t = _active;
    if (t == null) return;
    if (lat == 0 && lng == 0) return;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
    final samples = [
      ...t.gpsSamples,
      {
        't': now().millisecondsSinceEpoch ~/ 1000,
        'lat': lat,
        'lng': lng,
      },
    ];
    if (samples.length > maxGpsSamples) {
      samples.removeRange(0, samples.length - maxGpsSamples);
    }
    _active = ActiveTrip(
      vehicleId: t.vehicleId,
      startedAt: t.startedAt,
      source: t.source,
      gpsSamples: samples,
    );
    final last = _lastGpsPersist;
    if (last == null ||
        now().difference(last) >= gpsPersistInterval) {
      _lastGpsPersist = now();
      unawaited(_writeActive());
    }
  }

  Future<void> _endTrip({double? distanceKm}) async {
    final t = _active;
    if (t == null) return;
    _active = null;
    _pending = [
      ..._pending,
      PendingTrip(
        vehicleId: t.vehicleId,
        startedAt: t.startedAt,
        endedAt: now(),
        distanceKm: distanceKm,
        source: t.source,
        gpsSamples: t.gpsSamples,
      ),
    ];
    await _writeActive();
    await _writePending();
    unawaited(flush());
  }

  /// Tries to write all queued trips in order. A failure aborts (queue kept)
  /// so an offline drive re-syncs on the next opportunity. Idempotent.
  Future<void> flush() async {
    if (_flushing) return;
    _flushing = true;
    try {
      while (_pending.isNotEmpty) {
        final trip = _pending.first;
        try {
          await writeTrip(trip);
          _pending = _pending.sublist(1);
          await _writePending();
        } catch (_) {
          break;
        }
      }
    } finally {
      _flushing = false;
    }
  }
}
