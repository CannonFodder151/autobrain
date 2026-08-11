/// Keeps the app process alive while OBD trip recording is active.
///
/// On Android this runs a foreground service (with a notification) so the
/// main-isolate trip monitor keeps polling the Bluetooth adapter while the app
/// is backgrounded. Web/desktop get a no-op stub — the import below picks the
/// IO implementation only on platforms with `dart:io`, so the web build never
/// links the foreground-service plugin.
library;

import 'obd_keepalive_stub.dart'
    if (dart.library.io) 'obd_keepalive_io.dart' as impl;

class ObdKeepAlive {
  static bool get supported => impl.KeepAliveImpl.supported;

  /// Starts (or updates) the foreground service when supported.
  static Future<void> ensureRunning({
    String title = 'OBD recording',
    String text = 'Recording trips automatically',
  }) =>
      impl.KeepAliveImpl.ensureRunning(title: title, text: text);

  static Future<void> update({String? text}) =>
      impl.KeepAliveImpl.update(text: text);

  static Future<void> stop() => impl.KeepAliveImpl.stop();
}
