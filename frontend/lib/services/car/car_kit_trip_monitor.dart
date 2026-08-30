/// Phone-side driving detection (AUT-367): auto start/stop logbook trips from
/// a head-unit / car-kit Bluetooth connection, guarded by GPS speed.
///
/// This is the complementary phone path to the OBD/VGate dongle path
/// (AUT-362). Both converge on one shared auto start/stop service — the
/// [ObdTripRecorder] — via its [ObdTripRecorder.feedCarConnection] seam. This
/// monitor is deterministic (no AI): it treats the car-kit BT link as the
/// start trigger, requires GPS speed above a threshold for a sustained window
/// before committing a trip (so a passenger in a bus doesn't start one), and
/// closes the trip when the link drops or the car goes quiet. Distance is
/// accumulated from GPS speed (the phone-path "odometer diff").
///
/// Pure Dart with zero Flutter/BT imports so the state machine unit-tests
/// without hardware. The platform glue (Android BT receiver + GPS) feeds the
/// pure sources [CarKitConnection] and [SpeedSource]; tests inject fakes.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../obd/obd_keepalive.dart';
import '../obd/obd_trip_recorder.dart';

/// The car-kit / head-unit BT link state. Deterministic, platform-provided.
enum CarKitLinkState { disconnected, connected }

/// A source of car-kit connection events (Android ACL broadcasts). Injected so
/// tests can drive the monitor without a real Bluetooth radio.
abstract class CarKitConnection {
  Stream<CarKitLinkState> get stateChanges;
}

/// A source of GPS speed samples (km/h). Injected for tests.
abstract class SpeedSource {
  Stream<double> get speedKmh;
}

/// A live source is optional at construction; the monitor also exposes the
/// [feedConnection]/[feedSpeed] methods so callers (or tests) can push
/// events synchronously.
class CarKitTripMonitor extends ChangeNotifier {
  CarKitTripMonitor({
    required this.recorder,
    CarKitConnection? connection,
    SpeedSource? speed,
    DateTime Function()? now,
    this.commitSpeedKmh = 20,
    this.commitSeconds = 5,
    this.stopSpeedKmh = 5,
    this.stopSeconds = 20,
  }) : now = now ?? DateTime.now {
    if (connection != null) _subscribeConnection(connection);
    if (speed != null) _subscribeSpeed(speed);
  }

  final ObdTripRecorder recorder;
  final DateTime Function() now;

  /// Speed (km/h) that must be sustained for [commitSeconds] while the car-kit
  /// link is up before a trip starts.
  final double commitSpeedKmh;

  /// Sustained speed window (seconds) required to commit a trip start.
  final int commitSeconds;

  /// Below this speed (km/h) for [stopSeconds] the trip is closed (car parked
  /// but the head unit is still linked / ignition off).
  final double stopSpeedKmh;

  /// Sustained below-[stopSpeedKmh] window (seconds) that closes the trip.
  final int stopSeconds;

  CarKitLinkState _link = CarKitLinkState.disconnected;
  CarKitLinkState get link => _link;

  bool _enabled = false;

  /// Gates the whole phone path; the "Auto-start trip logging when connected
  /// to the car" switch (AUT-366) drives this. Off = link/speed ignored.
  bool get enabled => _enabled;
  set enabled(bool value) {
    if (_enabled == value) return;
    _enabled = value;
    if (!value) {
      unawaited(_closeTrip());
    }
    if (!_disposed) notifyListeners();
  }

  /// The GPS odometer accumulated while a trip is active, in km.
  double _distanceKm = 0;
  double get distanceKm => _distanceKm;

  bool get isTripActive => recorder.isTripActive;

  final List<StreamSubscription<dynamic>> _subs = [];

  void _subscribeConnection(CarKitConnection connection) {
    _subs.add(connection.stateChanges.listen(
      (s) => feedConnection(s),
      onError: (_) {},
    ));
  }

  void _subscribeSpeed(SpeedSource speed) {
    _subs.add(speed.speedKmh.listen(
      (s) => feedSpeed(s),
      onError: (_) {},
    ));
  }

  // --- Speed-guard window state ------------------------------------------

  bool _speedWindowOpen = false;
  DateTime? _windowStartedAt;
  DateTime? _stopWatchStartedAt;

  /// Feeds a car-kit link state change from the platform layer.
  Future<void> feedConnection(CarKitLinkState state) async {
    if (state == _link) return;
    _link = state;
    switch (state) {
      case CarKitLinkState.connected:
        // Link up: start the motion guard window. No trip yet.
        if (_enabled) _resetSpeedWindow();
      case CarKitLinkState.disconnected:
        // Link dropped (ignition off / head unit off): close any open trip.
        await _closeTrip();
    }
    if (!_disposed) notifyListeners();
  }

  /// Feeds one GPS speed sample (km/h). While the link is up this drives the
  /// speed guard; while a trip is active it accumulates the odometer diff.
  Future<void> feedSpeed(double speedKmh) async {
    if (!_enabled) return;
    final t = now();
    if (_link == CarKitLinkState.connected && !recorder.isTripActive) {
      await _updateSpeedWindow(speedKmh, t);
    } else if (recorder.isTripActive) {
      await _trackStop(speedKmh, t);
    }
  }

  void _resetSpeedWindow() {
    _speedWindowOpen = false;
    _windowStartedAt = null;
    _stopWatchStartedAt = null;
    _lastSampleTime = null;
    _distanceKm = 0;
  }

  Future<void> _updateSpeedWindow(double speedKmh, DateTime t) async {
    if (speedKmh >= commitSpeedKmh) {
      if (!_speedWindowOpen) {
        _speedWindowOpen = true;
        _windowStartedAt = t;
      } else if (t.difference(_windowStartedAt!).inSeconds >= commitSeconds) {
        await _commitTrip();
      }
    } else {
      _speedWindowOpen = false;
      _windowStartedAt = null;
    }
  }

  Future<void> _commitTrip() async {
    if (recorder.isTripActive) return;
    _speedWindowOpen = false;
    _windowStartedAt = null;
    _distanceKm = 0;
    _lastSampleTime = null;
    await recorder.feedCarConnection(CarConnectionState.connected,
        source: 'car_auto');
    await _syncKeepAlive();
    if (!_disposed) notifyListeners();
  }

  Future<void> _trackStop(double speedKmh, DateTime t) async {
    // Odometer diff: integrate speed over each sample. Samples are pushed
    // roughly once a second; speed km/h * (dt in h) = km.
    final last = _lastSampleTime;
    if (last != null) {
      final dtHours = t.difference(last).inMilliseconds / 3600000.0;
      if (dtHours > 0) _distanceKm += speedKmh * dtHours;
    }
    _lastSampleTime = t;
    if (speedKmh < stopSpeedKmh) {
      _stopWatchStartedAt ??= t;
      if (t.difference(_stopWatchStartedAt!).inSeconds >= stopSeconds) {
        await _closeTrip();
      }
    } else {
      _stopWatchStartedAt = null;
    }
  }

  DateTime? _lastSampleTime;

  Future<void> _closeTrip() async {
    if (!recorder.isTripActive) return;
    _stopWatchStartedAt = null;
    _lastSampleTime = null;
    final d = _distanceKm;
    _distanceKm = 0;
    await recorder.feedCarConnection(
      CarConnectionState.disconnected,
      distanceKm: d,
      source: 'car_auto',
    );
    await _syncKeepAlive();
    if (!_disposed) notifyListeners();
  }

  bool _keepAliveOn = false;

  /// Foreground service keeps the phone path alive only while a trip is open
  /// (BT ACL broadcasts still wake the app; the service covers the app being
  /// backgrounded mid-drive). No drain while parked. Best-effort: a missing
  /// foreground-service plugin (unit tests, web) is non-fatal.
  Future<void> _syncKeepAlive() async {
    try {
      if (recorder.isTripActive) {
        const text = 'Trip recording…';
        if (_keepAliveOn) {
          await ObdKeepAlive.update(text: text);
        } else {
          _keepAliveOn = true;
          await ObdKeepAlive.ensureRunning(title: 'Car connected', text: text);
        }
      } else if (_keepAliveOn) {
        _keepAliveOn = false;
        await ObdKeepAlive.stop();
      }
    } catch (_) {
      _keepAliveOn = false;
    }
  }

  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    for (final s in _subs) {
      s.cancel();
    }
    super.dispose();
  }
}
