/// Singleton orchestrator for automatic OBD trip recording (GoFar-style).
///
/// Owns the shared [ObdConnection] and [ObdTripRecorder]: loads the user's OBD
/// settings, auto-connects to the last adapter (with reconnect backoff), polls
/// live PIDs every 2 s and feeds ignition samples into the recorder, ends
/// trips on BT link-drop, and runs the foreground-service keep-alive so
/// recording continues while the app is backgrounded.
///
/// The UI (`ObdScreen`) reflects this monitor instead of owning its own
/// connection, so one poll loop drives both the live readings and the trip
/// recorder with no double Bluetooth traffic.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api_client.dart';
import '../../core/token_store.dart';
import 'elm327.dart';
import 'obd_connection.dart';
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
    ObdConnection? connection,
    ObdTripRecorder? recorder,
    Future<ApiClient> Function()? apiFactory,
    this.pollInterval = const Duration(seconds: 2),
    this.reconnectInterval = const Duration(seconds: 30),
  })  : connection = connection ?? ObdConnection(),
        recorder = recorder ?? _buildRecorder(apiFactory) {
    this.connection.addListener(_onConnectionChanged);
  }

  static ObdTripMonitor? _instance;
  static ObdTripMonitor get instance => _instance ??= ObdTripMonitor();

  final ObdConnection connection;
  final ObdTripRecorder recorder;
  final Duration pollInterval;
  final Duration reconnectInterval;

  String? _vehicleId;
  bool _enabled = false;
  bool _autoConnect = false;
  bool _reconnectPaused = false;
  Set<String>? _supported;
  List<PidReading> _live = const [];
  Timer? _poll;
  Timer? _reconnect;
  bool _keepAliveOn = false;
  bool _disposed = false;

  bool get armed => _vehicleId != null;
  bool get enabled => _enabled;
  bool get autoConnect => _autoConnect;
  List<PidReading> get live => _live;
  Set<String>? get supported => _supported;

  /// One-time app-start hook: re-arms the last used vehicle so auto-connect
  /// and any buffered mid-drive trip resume without opening the OBD screen.
  Future<void> start() async {
    if (_disposed || _started) return;
    _started = true;
    final prefs = await SharedPreferences.getInstance();
    final vehicleId = prefs.getString(lastVehicleKey);
    if (vehicleId == null) return;
    await arm(vehicleId);
  }

  bool _started = false;

  /// Binds the vehicle, reads the persisted OBD flags, resumes any buffered
  /// trip, flushes queued syncs and starts auto-connect + polling. Safe to
  /// call repeatedly.
  Future<void> arm(String vehicleId) async {
    if (_disposed) return;
    _reconnectPaused = false;
    if (_vehicleId != vehicleId) {
      _vehicleId = vehicleId;
      recorder.bind(vehicleId);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(lastVehicleKey, vehicleId);
    }
    final prefs = await SharedPreferences.getInstance();
    _enabled = prefs.getBool('obd_enabled') ?? false;
    _autoConnect = prefs.getBool('obd_auto_connect') ?? false;
    await recorder.restore();
    await recorder.flush();
    _syncKeepAlive();
    if (_enabled && _autoConnect) _connectOrSchedule();
  }

  static const lastVehicleKey = 'obd_last_vehicle';

  /// Applies the admin-granted OBD access flag (persisted by the OBD screen).
  void setEnabled(bool enabled) {
    _enabled = enabled;
    if (!enabled) {
      _reconnect?.cancel();
      _reconnectPaused = true;
    }
  }

  /// Applies the user's auto-connect preference (persisted by the OBD screen).
  void setAutoConnect(bool autoConnect) {
    _autoConnect = autoConnect;
    if (autoConnect && _enabled) {
      _connectOrSchedule();
    } else {
      _reconnect?.cancel();
    }
  }

  /// Connects to the remembered adapter, or schedules a retry (the adapter is
  /// asleep while the car is off — the connect fails harmlessly).
  Future<void> _connectOrSchedule() async {
    if (_disposed || _reconnectPaused || connection.isConnected) return;
    final adapter = await connection.lastAdapter();
    if (adapter == null) return;
    _reconnect?.cancel();
    try {
      await connection.connect(adapter);
    } catch (_) {}
    if (!connection.isConnected) _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_disposed || _reconnectPaused || !_enabled || !_autoConnect) return;
    _reconnect?.cancel();
    _reconnect = Timer(reconnectInterval, _connectOrSchedule);
  }

  /// Explicit user disconnect: pauses auto-reconnect until the next [arm] or
  /// a manual [connect].
  Future<void> disconnect() async {
    _reconnectPaused = true;
    _reconnect?.cancel();
    await connection.disconnect();
    _syncKeepAlive();
  }

  /// Explicit user connect (from the device picker).
  Future<void> connect(ObdAdapter adapter) async {
    _reconnectPaused = false;
    _reconnect?.cancel();
    await connection.connect(adapter);
  }

  void _onConnectionChanged() {
    if (_disposed) return;
    if (connection.isConnected) {
      _reconnect?.cancel();
      _startPolling();
      unawaited(_learnSupported());
    } else {
      _stopPolling();
      _live = const [];
      // A drop while we were connected (adapter sleeping after ignition-off)
      // is the strongest ignition-off signal — close any open trip, then let
      // auto-connect pick the next drive up.
      unawaited(recorder.onLinkDrop());
      _syncKeepAlive();
      if (_enabled && _autoConnect && !_reconnectPaused) _scheduleReconnect();
    }
    notifyListeners();
  }

  void _startPolling() {
    _poll?.cancel();
    _poll = Timer.periodic(pollInterval, (_) => _pollOnce());
  }

  void _stopPolling() {
    _poll?.cancel();
    _poll = null;
  }

  Future<void> _learnSupported() async {
    final session = connection.session;
    if (session == null) return;
    try {
      final supported = await session.readSupportedPids();
      if (_disposed) return;
      _supported = supported;
      notifyListeners();
    } catch (_) {}
  }

  Future<void> _pollOnce() async {
    final session = connection.session;
    if (session == null) return;
    if (!session.isConnected) {
      await connection.markDropped();
      return;
    }
    try {
      final readings = await session.readLive(supported: _supported);
      if (_disposed || !connection.isConnected) return;
      if (!session.isConnected) {
        await connection.markDropped();
        return;
      }
      _live = readings;
      double? voltage;
      double? rpm;
      for (final r in readings) {
        // 0 V means the ECU does not implement PID 42 — treat as no signal.
        if (r.pid.command == '0142' && r.value > 0.5) {
          voltage = r.value.toDouble();
        }
        if (r.pid.command == '010C') rpm = r.value.toDouble();
      }
      recorder.feed(IgnitionSample(voltage: voltage, rpm: rpm));
      _syncKeepAlive();
      notifyListeners();
    } catch (_) {
      // Adapter dropped mid-reply (sleeping) — close the trip, show it as a
      // disconnect, and let auto-connect retry.
      if (!session.isConnected) await connection.markDropped();
    }
  }

  /// Foreground service keeps the process alive only while there is something
  /// to record (connected, trip open, or a pending sync) — no battery drain
  /// while the car is off and the adapter is asleep.
  void _syncKeepAlive() {
    if (_disposed) return;
    final needed = connection.isConnected ||
        recorder.isTripActive ||
        recorder.pending.isNotEmpty;
    if (needed) {
      final text = recorder.isTripActive ? 'Trip recording…' : 'OBD connected';
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
    _reconnect?.cancel();
    _poll?.cancel();
    await recorder.flush();
    await connection.disconnect();
    if (_keepAliveOn) {
      _keepAliveOn = false;
      await ObdKeepAlive.stop();
    }
    connection.removeListener(_onConnectionChanged);
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
      'reason': 'Auto-logged (OBD)',
      'source': 'obd_auto',
    });
    final id = (created as Map<String, dynamic>)['id'] as String;
    await api.patch('$base/$id', {
      'ended_at': trip.endedAt.toUtc().toIso8601String(),
      'status': 'completed',
      'source': 'obd_auto',
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
