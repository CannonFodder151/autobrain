/// No-op keep-alive for platforms without a foreground-service plugin (web).
/// See [obd_keepalive_io.dart] for the Android implementation.
library;

class KeepAliveImpl {
  static const bool supported = false;

  static Future<void> ensureRunning({String? title, String? text}) async {}

  static Future<void> update({String? text}) async {}

  static Future<void> stop() async {}
}
