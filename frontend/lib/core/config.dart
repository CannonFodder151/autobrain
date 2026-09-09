import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Runtime configuration.
///
/// The base URLs are compiled in via --dart-define as defaults. On mobile the
/// user can override them at runtime via the server picker (stored in
/// SharedPreferences) so a single APK can target the hosted subscription or
/// any self-hosted server. On web/desktop the compiled URL is always used.
class AppConfig {
  static const String _defaultApiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://hosted.autobrainservice.app/api/v1',
  );
  static const String _defaultWsBase = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'wss://hosted.autobrainservice.app/ws',
  );

  static const String _prefsKey = 'server_config';

  /// Whether a server has been resolved yet (picker only runs on mobile).
  static bool serverConfigured = false;

  /// Result of the last [validate] call. `null` until [validate] has run at
  /// least once. Surfaced by the kDebugMode MaterialBanner in `app.dart` so
  /// QA/dev can confirm the resolved backend is reachable at boot.
  static bool? lastValidationOk;

  /// Human-readable error from the last [validate] call. `null` on success or
  /// when validation has not run yet.
  static String? lastValidationError;

  static String apiBase = _defaultApiBase;
  static String wsBase = _defaultWsBase;

  /// Whether running natively on Android/iOS (as opposed to web/desktop).
  static bool get isMobile =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  /// Loads a saved server selection (called once at startup).
  static Future<void> load() async {
    // Web and desktop always use the compiled base URL — no picker.
    if (!isMobile) {
      serverConfigured = true;
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefsKey);
    if (saved != null && saved.isNotEmpty) {
      final parts = saved.split('|');
      if (parts.length == 2) {
        apiBase = parts[0];
        wsBase = parts[1];
        serverConfigured = true;
        return;
      }
    }
    // Demo build is pre-wired to the demo instance — no picker needed.
    if (_defaultApiBase.contains('demo.autobrainservice.app')) {
      serverConfigured = true;
    }
  }

  /// Persists the chosen server and applies it immediately.
  static Future<void> setServer({
    required String apiBaseUrl,
    required String wsBaseUrl,
  }) async {
    apiBase = apiBaseUrl;
    wsBase = wsBaseUrl;
    serverConfigured = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, '$apiBaseUrl|$wsBaseUrl');
  }

  /// Builds API/WS base URLs from a custom server host + optional port.
  /// `secure=true` uses https/wss (typical for 443), otherwise http/ws.
  static ({String api, String ws}) customBase(
      String host, int? port, bool secure) {
    final scheme = secure ? 'https' : 'http';
    final wsScheme = secure ? 'wss' : 'ws';
    final authority = port == null || port == (secure ? 443 : 80)
        ? host
        : '$host:$port';
    return (
      api: '$scheme://$authority/api/v1',
      ws: '$wsScheme://$authority/ws',
    );
  }

  /// Hosted subscription target.
  static const hostedApi = 'https://hosted.autobrainservice.app/api/v1';
  static const hostedWs = 'wss://hosted.autobrainservice.app/ws';

  /// Probes the configured API base to confirm it is reachable at app boot.
  /// Sets [lastValidationOk] and [lastValidationError] (idempotent — call
  /// again after a server-pick to re-validate). Failures do not throw;
  /// `main.dart` inspects the result and decides whether to mount the
  /// misconfigured-backend screen.
  ///
  /// The probe hits `${apiOrigin}/healthz` (FastAPI convention) and accepts
  /// any 2xx/3xx response. Network errors and timeouts are reported via
  /// [lastValidationError]. Caller passes the [http.Client] so tests can
  /// inject a `MockClient`.
  static Future<void> validate({
    http.Client? client,
    Duration timeout = const Duration(seconds: 5),
  }) async {
    final origin = _apiOrigin();
    if (origin == null) {
      lastValidationOk = false;
      lastValidationError = 'apiBase is not a valid URL: $apiBase';
      return;
    }
    final healthUrl = Uri(
      scheme: origin.scheme,
      host: origin.host,
      port: origin.hasPort ? origin.port : null,
      path: '/healthz',
    );
    final c = client ?? http.Client();
    try {
      final resp = await c.get(healthUrl).timeout(timeout);
      if (resp.statusCode >= 200 && resp.statusCode < 400) {
        lastValidationOk = true;
        lastValidationError = null;
      } else {
        lastValidationOk = false;
        lastValidationError = 'HTTP ${resp.statusCode} from $healthUrl';
      }
    } on TimeoutException {
      lastValidationOk = false;
      lastValidationError =
          'timeout after ${timeout.inSeconds}s reaching $healthUrl';
    } catch (e) {
      lastValidationOk = false;
      lastValidationError = '$e';
    } finally {
      if (client == null) c.close();
    }
  }

  /// Strips the trailing `/api/v1` (or whatever path the URL carries) and
  /// returns the bare origin `scheme://host[:port]`. Returns `null` when the
  /// configured value is not a parseable absolute URL.
  static Uri? _apiOrigin() {
    final raw = apiBase.trim();
    if (raw.isEmpty) return null;
    final parsed = Uri.tryParse(raw);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) return null;
    return Uri(
      scheme: parsed.scheme,
      host: parsed.host,
      port: parsed.hasPort ? parsed.port : null,
    );
  }
}
