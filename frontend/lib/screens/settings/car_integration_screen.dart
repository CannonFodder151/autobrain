/// Mobile-only "Car Play / Android Auto Integration" settings submenu.
///
/// Honest explainer of what car integration can and cannot do — head-unit OBD
/// gauges and CarPlay OBD are blocked by Google/Apple category policy (see
/// AUT-364 research) — plus the "auto-start trip logging when connected to
/// the car" master toggle and a connection / last-trip status line.
///
/// Mobile-only by design: the entry point in the shared Settings screen is
/// guarded with `!kIsWeb`, and this file is not referenced by the web build's
/// navigation paths. It is safe to keep in the shared lineage so the
/// sync-mobile bot never clobbers it.
library;

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../services/car/car_kit_service.dart';
import '../../services/car/car_kit_trip_monitor.dart';
import '../../services/obd/obd_trip_monitor.dart';

/// Formats the submenu status line from live monitor state. Pure so it unit
/// tests without a running connection.
String carIntegrationStatusLine({
  required bool tripActive,
  DateTime? tripStartedAt,
  DateTime? lastTripAt,
  CarKitLinkState carKitLink = CarKitLinkState.disconnected,
}) {
  final base = switch (carKitLink) {
    CarKitLinkState.connected => 'Car-kit connected',
    CarKitLinkState.disconnected => 'Not connected',
  };
  if (tripActive) {
    final t = tripStartedAt?.toLocal();
    return t == null
        ? '$base · recording'
        : '$base · recording since ${_fmtTrip(t)}';
  }
  if (lastTripAt != null) {
    return '$base · last auto trip ${_fmtTrip(lastTripAt.toLocal())}';
  }
  return base;
}

String _fmtTrip(DateTime t) {
  final d = t.day.toString().padLeft(2, '0');
  final mo = t.month.toString().padLeft(2, '0');
  final h = t.hour.toString().padLeft(2, '0');
  final mi = t.minute.toString().padLeft(2, '0');
  return '$d/$mo $h:$mi';
}

class CarIntegrationScreen extends StatefulWidget {
  const CarIntegrationScreen({super.key, this.monitor});

  /// Injectable for tests; defaults to the shared [ObdTripMonitor].
  final ObdTripMonitor? monitor;

  @override
  State<CarIntegrationScreen> createState() => _CarIntegrationScreenState();
}

class _CarIntegrationScreenState extends State<CarIntegrationScreen> {
  static const prefKey = 'car_auto_trip_logging';
  static const lastTripKey = 'car_last_trip_at';

  late final ObdTripMonitor _monitor =
      widget.monitor ?? ObdTripMonitor.instance;
  late final CarKitTripMonitor? _carKitMonitor =
      CarKitTripMonitorService.instance.monitor;

  bool _autoLogging = false;
  DateTime? _lastTripAt;

  @override
  void initState() {
    super.initState();
    _monitor.addListener(_onChanged);
    _carKitMonitor?.addListener(_onChanged);
    _load();
  }

  @override
  void dispose() {
    _monitor.removeListener(_onChanged);
    _carKitMonitor?.removeListener(_onChanged);
    super.dispose();
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _autoLogging = prefs.getBool(prefKey) ?? false;
      final last = prefs.getString(lastTripKey);
      _lastTripAt = last == null ? null : DateTime.tryParse(last);
    });
  }

  Future<void> _setAutoLogging(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    setState(() => _autoLogging = value);
    await prefs.setBool(prefKey, value);
    // The master switch drives the phone car-kit BT + GPS path (AUT-367),
    // which needs no OBD adapter.
    await CarKitTripMonitorService.instance.setEnabled(value);
  }

  @override
  Widget build(BuildContext context) {
    final r = _monitor.recorder;
    final carKitLink = _carKitMonitor?.link ?? CarKitLinkState.disconnected;
    final status = carIntegrationStatusLine(
      tripActive: r.isTripActive,
      tripStartedAt: r.activeTrip?.startedAt,
      lastTripAt: _lastTripAt,
      carKitLink: carKitLink,
    );
    return Scaffold(
      appBar: AppBar(title: const Text('Car Play / Android Auto')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('What works',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.route, color: Colors.green),
              title: const Text('Auto trip logging'),
              subtitle: const Text(
                  'When your phone connects to the car, drives are logged to '
                  'the logbook automatically. Android: when the phone links to '
                  'the car\'s Bluetooth (head unit / car-kit), a drive is '
                  'logged once moving — no Android Auto approval or OBD adapter '
                  'needed.'),
            ),
          ),
          const SizedBox(height: 16),
          const Text('What doesn\'t work (yet)',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                const ListTile(
                  leading: Icon(Icons.dashboard_outlined, color: Colors.grey),
                  title: Text('Head-unit OBD gauges'),
                  subtitle: Text(
                      'Android Auto and CarPlay don\'t allow OBD / '
                      'diagnostics apps, so gauge clusters on the car screen '
                      'aren\'t possible today (Google/Apple category policy).'),
                ),
                const Divider(height: 1),
                const ListTile(
                  leading: Icon(Icons.no_crash_outlined, color: Colors.grey),
                  title: Text('CarPlay OBD'),
                  subtitle: Text(
                      'OBD is Android-only (Bluetooth Classic SPP; iOS '
                      'forbids it), so CarPlay OBD isn\'t supported.'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          const Text('Trip logging',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: SwitchListTile(
              secondary: Icon(_autoLogging
                  ? Icons.settings_backup_restore
                  : Icons.settings_backup_restore_outlined),
              title: const Text('Auto-start trip logging when connected '
                  'to the car'),
              subtitle: Text(_autoLogging
                  ? 'On — trips start when the phone connects to the car and '
                      'it starts moving.'
                  : 'Off — trips are only logged manually.'),
              value: _autoLogging,
              onChanged: _setAutoLogging,
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.info_outline),
              title: const Text('Status'),
              subtitle: Text(status),
            ),
          ),
          const SizedBox(height: 16),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8),
            child: Text(
              'How it works: Android Auto projects your phone to the car '
              'screen — trip logging runs in the background on the phone, so '
              'it needs no Android Auto app approval. iOS / CarPlay support '
              'will follow (a BLE adapter is required).',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
        ],
      ),
    );
  }
}
