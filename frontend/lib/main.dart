import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/auth_state.dart';
import 'core/config.dart';
import 'services/obd/obd_trip_monitor.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppConfig.load();
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
}
