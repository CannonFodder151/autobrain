import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/auth_state.dart';
import 'core/config.dart';
import 'services/car/car_kit_service.dart';
import 'services/obd/obd_trip_monitor.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Capture the deep-link fragment before runApp: the Flutter web engine
  // clears `#/license` via history.replaceState within ~2-4s of load, after
  // which licenseRequested() would read an empty fragment (AUT-629).
  AutoBrainApp.initialFragment = Uri.base.fragment;
  await AppConfig.load();
  // AUT-2192: fail-fast on a misconfigured build. Web/desktop have no server
  // picker so a wrong URL silently talks to a wrong host; we surface it now.
  // On mobile a release build only runs the probe when the user has not yet
  // picked a server; once the picker has stored a value, an in-app outage
  // surfaces via the existing error banners instead of a hard boot block.
  if (AppConfig.serverConfigured) {
    final v = await AppConfig.validate();
    if (!v.ok) {
      runApp(_MisconfigApp(error: v.error ?? 'unknown', apiBase: v.apiBase));
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

/// Minimal app shown when AppConfig.validate() fails at boot. Renders the
/// resolved URL + error so a misconfigured build is obvious without reading
/// build logs (AUT-2192).
class _MisconfigApp extends StatelessWidget {
  final String error;
  final String apiBase;
  const _MisconfigApp({required this.error, required this.apiBase});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AutoBrain — misconfigured',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.light(),
      dark: ThemeData.dark(),
      home: Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'AutoBrain is misconfigured',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 16),
                Text('API base: $apiBase'),
                const SizedBox(height: 8),
                Text('Error: $error'),
                const SizedBox(height: 24),
                const Text(
                  'Rebuild with the correct --dart-define=API_BASE_URL=... '
                  'and --dart-define=WS_BASE_URL=... (see docker/frontend/Dockerfile '
                  'or scripts/publish-images.sh).',
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
