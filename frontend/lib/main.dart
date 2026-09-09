import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/auth_state.dart';
import 'core/config.dart';
import 'core/misconfigured_backend_screen.dart';
import 'services/car/car_kit_service.dart';
import 'services/obd/obd_trip_monitor.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Capture the deep-link fragment before runApp: the Flutter web engine
  // clears `#/license` via history.replaceState within ~2-4s of load, after
  // which licenseRequested() would read an empty fragment (AUT-629).
  AutoBrainApp.initialFragment = Uri.base.fragment;
  await AppConfig.load();
  // AUT-2352: boot-time reachability probe (release builds only — debug
  // builds skip the probe so hot-reload stays snappy and dev can point at a
  // half-up backend without the misconfigured screen blocking every load).
  // Failure mounts MisconfiguredBackendScreen; success falls through to the
  // normal AutoBrainApp.
  if (!kDebugMode) {
    await AppConfig.validate();
    if (AppConfig.lastValidationOk == false) {
      runApp(
        ChangeNotifierProvider(
          create: (_) => AuthState(),
          child: const MisconfiguredBackendScreen(),
        ),
      );
      return;
    }
  }
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState(),
      child: const AutoBrainApp(),
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
