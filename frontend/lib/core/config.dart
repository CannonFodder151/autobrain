import 'package:flutter/foundation.dart';
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
}
