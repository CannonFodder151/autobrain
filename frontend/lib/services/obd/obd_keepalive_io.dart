/// Android foreground-service keep-alive for OBD trip recording.
///
/// Runs a low-importance notification service (type `connectedDevice`, the
/// Android 14+ requirement for Bluetooth) that keeps the process alive so the
/// main-isolate trip monitor keeps sampling the adapter while the app is
/// backgrounded. Battery-friendly: the monitor starts/stops this only while a
/// BT session or a trip is live, and the adapter itself sleeps when the car is
/// off. iOS is intentionally a no-op — the VGate iCar Pro is Bluetooth Classic
/// which iOS apps cannot use (see docs/obd-integration.md).
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

class KeepAliveImpl {
  static bool get supported =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  static bool _initialized = false;

  static Future<void> ensureRunning({String? title, String? text}) async {
    if (!supported) return;
    await _init();
    final started = await FlutterForegroundTask.startService(
      serviceTypes: const [ForegroundServiceTypes.connectedDevice],
      notificationTitle: title ?? 'OBD recording',
      notificationText: text ?? 'Recording trips automatically',
    );
    if (started is ServiceRequestFailure) {
      // Service already running or permission pending — the recorder still
      // works while the app is foregrounded, so this is non-fatal.
      if (started.error is! ServiceAlreadyStartedException) {
        debugPrint('foreground service: ${started.error}');
      }
    }
  }

  static Future<void> update({String? text}) async {
    if (!supported) return;
    await _init();
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.updateService(notificationText: text);
    }
  }

  static Future<void> stop() async {
    if (!supported) return;
    await _init();
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  static Future<void> _init() async {
    if (_initialized) return;
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'obd_trip_recording',
        channelName: 'OBD trip recording',
        channelDescription:
            'Keeps automatic trip recording running in the background.',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        autoRunOnBoot: false,
        allowWakeLock: false,
      ),
    );
    _initialized = true;
  }
}
