/// Singleton orchestrator for automatic trip recording (GoFar-style).
///
/// Hosts the shared [ObdTripRecorder] used by the phone-side car-kit /
/// head-unit auto-trip path (AUT-367): loads the last used vehicle, resumes
/// any buffered mid-drive trip, flushes queued syncs, and runs the
/// foreground-service keep-alive while there is something to record.
///
/// Generic ELM327/BT-SPP adapter support was removed (AUT-427): trips are
/// started/stopped from the car-kit BT + GPS path only, so no adapter
/// connection or PID polling lives here anymore.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_client.dart';
import '../../core/token_store.dart';
import 'obd_keepalive.dart';
import 'obd_trip_recorder.dart';

/// SharedPreferences-backed [TripStore] (survives app kills).
class PrefsTripStore implements TripStore {
  PrefsTripStore(this._prefs);
  final SharedPreferences _prefs;

  @override
  Future<String?> read(String key) async => _prefs.getString(key);

  @override
  Future<void> write(String key, String value) async {
    await _prefs.setString(key, value);
  }
}

class ObdTripMonitor extends ChangeNotifier {
  ObdTripMonitor({
    ObdTripRecorder? recorder,
    Future<ApiClient> Function()? apiFactory,
  }) : recorder = recorder ?? _buildRecorder(apiFactory);

  static ObdTripMonitor? _instance;
  static ObdTripMonitor get instance => _instance ??= ObdTripMonitor();

  final ObdTripRecorder recorder;

  String? _vehicleId;
  bool _keepAliveOn = false;
  bool _disposed = false;
  bool _started = false;

  bool get armed => _vehicleId != null;

  /// One-time app-start hook: re-arms the last used vehicle so any buffered
  /// mid-drive trip resumes without opening any screen.
  Future<void> start() async {
    if (_disposed || _started) return;
    _started = true;
    final prefs = await SharedPreferences.getInstance();
    final vehicleId = prefs.getString(lastVehicleKey);
    if (vehicleId == null) return;
    await arm(vehicleId);
  }

  /// Binds the vehicle, resumes any buffered trip and flushes queued syncs.
  /// Safe to call repeatedly.
  Future<void> arm(String vehicleId) async {
    if (_disposed) return;
    if (_vehicleId != vehicleId) {
      _vehicleId = vehicleId;
      recorder.bind(vehicleId);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(lastVehicleKey, vehicleId);
    }
    await recorder.restore();
    await recorder.flush();
    _syncKeepAlive();
  }

  static const lastVehicleKey = 'obd_last_vehicle';

  /// Foreground service keeps the process alive only while there is something
  /// to record (a trip open or a pending sync) — no battery drain while parked.
  void _syncKeepAlive() {
    if (_disposed) return;
    final needed = recorder.isTripActive || recorder.pending.isNotEmpty;
    if (needed) {
      final text = recorder.isTripActive ? 'Trip recording…' : 'Trip to sync';
      if (_keepAliveOn) {
        unawaited(ObdKeepAlive.update(text: text));
      } else {
        _keepAliveOn = true;
        unawaited(ObdKeepAlive.ensureRunning(text: text));
      }
    } else if (_keepAliveOn) {
      _keepAliveOn = false;
      unawaited(ObdKeepAlive.stop());
    }
  }

  Future<void> stop() async {
    if (_disposed) return;
    _disposed = true;
    await recorder.flush();
    if (_keepAliveOn) {
      _keepAliveOn = false;
      await ObdKeepAlive.stop();
    }
  }

  static ObdTripRecorder _buildRecorder(Future<ApiClient> Function()? apiFactory) {
    final factory = apiFactory ?? _defaultApiFactory;
    return ObdTripRecorder(
      store: _lazyStore,
      writeTrip: (trip) => _writeTrip(trip, factory),
    );
  }

  static Future<ApiClient> _defaultApiFactory() async {
    final (token, _, _) = await TokenStore().read();
    return ApiClient(token);
  }

  static Future<void> _writeTrip(
      PendingTrip trip, Future<ApiClient> Function() apiFactory) async {
    final api = await apiFactory();
    final base = '/vehicles/${trip.vehicleId}/logbook';
    final created = await api.post(base, {
      'started_at': trip.startedAt.toUtc().toIso8601String(),
      'reason':
          trip.source == 'car_auto' ? 'Auto-logged (Car Kit)' : 'Auto-logged (OBD)',
      'source': trip.source,
    });
    final id = (created as Map<String, dynamic>)['id'] as String;
    await api.patch('$base/$id', {
      'ended_at': trip.endedAt.toUtc().toIso8601String(),
      'status': 'completed',
      'source': trip.source,
      if (trip.distanceKm != null) 'distance_km': trip.distanceKm,
      if (trip.gpsSamples.isNotEmpty)
        'gps_samples': [
          for (final s in trip.gpsSamples)
            {'t': s['t'], 'lat': s['lat'], 'lon': s['lng']}
        ],
    });
    // Remember the latest synced auto trip for the settings status line
    // (AUT-366 Car Play / Android Auto submenu).
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('car_last_trip_at', trip.endedAt.toIso8601String());
  }
}

/// Lazily opens SharedPreferences on first touch (recorder state may be
/// restored before the plugin binding is fully ready at app start).
final TripStore _lazyStore = _LazyPrefsTripStore();

class _LazyPrefsTripStore implements TripStore {
  Future<SharedPreferences>? _prefs;
  Future<SharedPreferences> get _instance =>
      _prefs ??= SharedPreferences.getInstance();

  @override
  Future<String?> read(String key) async => (await _instance).getString(key);

  @override
  Future<void> write(String key, String value) async {
    final p = await _instance;
    await p.setString(key, value);
  }
}
