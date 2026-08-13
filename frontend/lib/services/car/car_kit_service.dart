/// Singleton orchestrator for the phone-side auto trip path (AUT-367).
///
/// Owns the [CarKitTripMonitor] and its platform sources (car-kit BT ACL
/// connection + GPS speed), and binds it to the SAME [ObdTripRecorder] that
/// the OBD/VGate path (AUT-362) uses — both triggers converge on one shared
/// auto start/stop service. It re-arms the last used vehicle on app start so a
/// drive begins recording without opening any screen.
library;

import 'package:shared_preferences/shared_preferences.dart';

import '../obd/obd_trip_monitor.dart';
import 'car_kit_connection.dart';
import 'car_kit_trip_monitor.dart';
import 'speed_source.dart';

class CarKitTripMonitorService {
  CarKitTripMonitorService._();

  static CarKitTripMonitorService? _instance;
  static CarKitTripMonitorService get instance =>
      _instance ??= CarKitTripMonitorService._();

  CarKitTripMonitor? _monitor;
  CarKitTripMonitor? get monitor => _monitor;

  bool _started = false;

  /// The master "Auto-start trip logging when connected to the car" switch
  /// (AUT-366). Persisted as `car_auto_trip_logging`.
  static const String enabledKey = 'car_auto_trip_logging';

  /// Applies the master switch to the phone path (no-op until armed).
  Future<void> setEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(enabledKey, value);
    _monitor?.enabled = value;
  }

  /// One-time app-start hook: re-arms the last used vehicle and starts the
  /// car-kit + GPS listeners. The monitor is inert until armed.
  Future<void> start() async {
    if (_started) return;
    _started = true;
    final prefs = await SharedPreferences.getInstance();
    final vehicleId = prefs.getString(ObdTripMonitor.lastVehicleKey);
    if (vehicleId == null) return;
    await arm(vehicleId);
    final enabled = prefs.getBool(enabledKey) ?? false;
    if (enabled) _monitor?.enabled = true;
  }

  /// Binds a vehicle and (re)starts the sources. Safe to call repeatedly —
  /// the OBD screen arms the shared vehicle via [ObdTripMonitor]; this mirrors
  /// it so the phone path logs to the same vehicle.
  Future<void> arm(String vehicleId) async {
    final recorder = ObdTripMonitor.instance.recorder;
    _monitor ??= CarKitTripMonitor(
      recorder: recorder,
      connection: CarKitConnectionSource.create(),
      speed: SpeedSourceFactory.create(),
    );
    recorder.bind(vehicleId);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(ObdTripMonitor.lastVehicleKey, vehicleId);
  }

  Future<void> stop() async {
    if (_started) {
      final m = _monitor;
      _monitor = null;
      if (m != null) {
        m.dispose();
      }
    }
    _started = false;
  }
}
