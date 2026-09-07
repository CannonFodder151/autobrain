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
  unawaited(OfflineCache.instance.clearExpired().catchError((_) {}));
  await AppConfig.validate();
  final bootError = AppConfig.lastValidationOk == false;
  final connectivity = ConnectivityService.instance;

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthState()),
        Provider<ConnectivityService>.value(value: connectivity),
      ],
      child: bootError
          ? const MisconfiguredBackendScreen()
          : const AutoBrainApp(),
    ),
  );

  ObdTripMonitor.instance.start();
  CarKitTripMonitorService.instance.start();
}
