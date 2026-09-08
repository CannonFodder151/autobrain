import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/auth_state.dart';
import 'core/config.dart';
import 'core/connectivity_service.dart';
import 'core/misconfigured_backend_screen.dart';
import 'core/offline_cache.dart';
import 'services/car/car_kit_service.dart';
import 'services/obd/obd_trip_monitor.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AutoBrainApp.initialFragment = Uri.base.fragment;
  await AppConfig.load();
  await ConnectivityService.instance.init();
  // Drop expired SQLite cache rows before the first screen reads them.
  // Best-effort; never blocks boot on failure.
  OfflineCache.instance.clearExpired().catchError((_) {});
  // Boot-time reachability probe (AUT-2272 M0). Failures do not throw — we
  // mount MisconfiguredBackendScreen so the user can retry instead of
  // staring at a blank window. Server picker + login still work once the
  // probe passes.
  await AppConfig.validate();
  final bootError = AppConfig.lastValidationOk == false;
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState(),
      child: bootError
          ? const MisconfiguredBackendScreen()
          : const AutoBrainApp(),
    ),
  );
  // Resume background OBD trip recording (auto-connect + any buffered trip)
  // without the user having to open the OBD screen. No-op when no vehicle has
  // been set up with an adapter yet.
  ObdTripMonitor.instance.start();
  // Phone-side auto trip path (AUT-367): re-arms the car-kit BT + GPS speed
  // monitor on the same recorder, so a drive starts logging without Android
  // Auto approval or an OBD adapter.
  CarKitTripMonitorService.instance.start();
}
