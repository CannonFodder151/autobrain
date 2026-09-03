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
    defaultValue: 'https://localhost:8000/api/v1',
  );
  static const String _defaultWsBase = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'wss://localhost:8000/ws',
  );

  static const String _prefsKey = 'server_config';

  /// Whether a server has been resolved yet (picker only runs on mobile).
  static bool serverConfigured = false;

  static String apiBase = _defaultApiBase;
  static String wsBase = _defaultWsBase;

  /// Latest validation error message (null = last validation succeeded).
  /// Surfaced via the misconfigured-backend screen so the user sees a clear
  /// error instead of a silent connection-refused loop.
  static String? lastValidationError;

  /// Result of the last [validate] call.
  static bool validated = false;

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

  /// Fail-fast startup reachability check.
  ///
  /// Probes the resolved [apiBase] with a short GET against the nearest
  /// backend endpoint that exists for every release (`/api/v1/openapi.json`,
  /// with `/health` as a fallback). Sets [lastValidationError] on failure so
  /// [MisconfiguredBackendScreen] can render a clear message instead of the
  /// user staring at a forever-loading spinner.
  ///
  /// Returns true when the URL is reachable, false otherwise. Never throws —
  /// all network/parse errors are captured into [lastValidationError].
  static Future<bool> validate({
    http.Client? client,
    Duration timeout = const Duration(seconds: 4),
  }) async {
    final parsed = Uri.tryParse(apiBase);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      lastValidationError =
          'API_BASE_URL is not a valid absolute URL: "$apiBase"';
      validated = false;
      return false;
    }
    final origin = parsed.replace(
      path: '',
      query: '',
      fragment: '',
    );
    final probes = <Uri>[
      origin.replace(path: '${parsed.path}/openapi.json'),
      origin.replace(path: '${parsed.path}/health'),
      origin,
    ];
    final httpClient = client ?? http.Client();
    try {
      for (final probe in probes) {
        try {
          final resp = await httpClient
              .get(probe, headers: const {'Accept': 'application/json'})
              .timeout(timeout);
          if (resp.statusCode >= 200 && resp.statusCode < 500) {
            // 2xx = real backend, 3xx = redirect, 4xx = auth/method but the
            // host answered. All prove the URL is resolvable + reachable.
            lastValidationError = null;
            validated = true;
            return true;
          }
        } catch (_) {
          // try the next probe shape
        }
      }
      lastValidationError =
          'Could not reach API at $apiBase (tried openapi.json, /health, origin). '
          'Check BACKEND_URL/API_BASE_URL was baked at build time and the host is up.';
      validated = false;
      return false;
    } finally {
      if (client == null) httpClient.close();
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
}