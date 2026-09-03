import 'dart:async';
import 'dart:convert';

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

  // ---- AUT-2192: build-time pin + boot reachability check ------------------

  /// Short timeout for the boot reachability probe. Deliberately small so a
  /// misconfigured build fails fast instead of hanging the splash screen.
  static const Duration _probeTimeout = Duration(seconds: 4);

  /// Result of a boot reachability check against the resolved API base.
  /// `ok` is the only field callers should branch on.
  static ConfigValidation? lastValidation;

  /// Returns a structured description of how the URL was sourced and where it
  /// came from. Surfaced in the debug banner so misconfigured builds are
  /// obvious without grepping build logs.
  static ConfigSource describe() {
    final api = apiBase;
    final fromDefine =
        api == _defaultApiBase && _defaultApiBase != 'https://localhost:8000/api/v1';
    return ConfigSource(
      apiBase: api,
      wsBase: wsBase,
      apiFromDartDefine: fromDefine,
      apiOverriddenAtRuntime: api != _defaultApiBase && !fromDefine,
    );
  }

  /// Probe the resolved API base for a `/health` response. Never throws;
  /// returns a [ConfigValidation] with a clear error string on failure so
  /// `main()` can render a diagnostic screen instead of an infinite spinner.
  /// Web/desktop always run this (compiled URL must be reachable). On mobile
  /// the picker would have already redirected an unconfigured build, so this
  /// is best-effort and a failure only blocks the UI when the user picked a
  /// server that has since gone down.
  static Future<ConfigValidation> validate({bool required = true}) async {
    final api = apiBase;
    Uri parsed;
    try {
      parsed = Uri.parse(api);
    } catch (e) {
      final v = ConfigValidation(
        ok: false,
        apiBase: api,
        error: 'API_BASE_URL is not a valid URL: $e',
      );
      lastValidation = v;
      return v;
    }
    if (parsed.host.isEmpty) {
      final v = ConfigValidation(
        ok: false,
        apiBase: api,
        error: 'API_BASE_URL has no host (got "$api")',
      );
      lastValidation = v;
      return v;
    }
    final healthUri = parsed.resolve('/health');
    try {
      final resp = await http
          .get(healthUri, headers: const {'Accept': 'application/json'})
          .timeout(_probeTimeout);
      final ok = resp.statusCode >= 200 && resp.statusCode < 300;
      final v = ConfigValidation(
        ok: ok,
        apiBase: api,
        statusCode: resp.statusCode,
        body: resp.body.isNotEmpty ? _truncate(resp.body, 200) : null,
        error: ok ? null : '/health returned ${resp.statusCode}',
      );
      lastValidation = v;
      return v;
    } on TimeoutException {
      final v = ConfigValidation(
        ok: false,
        apiBase: api,
        error: '/health timed out after ${_probeTimeout.inSeconds}s',
      );
      lastValidation = v;
      return v;
    } catch (e) {
      final v = ConfigValidation(
        ok: false,
        apiBase: api,
        error: e.toString(),
      );
      lastValidation = v;
      return v;
    }
  }

  static String _truncate(String s, int max) =>
      s.length <= max ? s : '${s.substring(0, max)}…';

  // ponytail: probing via /health couples the boot check to the backend
  // contract. If we ever add a static `/version.txt` or a CORS preflight head
  // probe, swap `_probe()` in.
}

class ConfigSource {
  final String apiBase;
  final String wsBase;
  final bool apiFromDartDefine;
  final bool apiOverriddenAtRuntime;
  const ConfigSource({
    required this.apiBase,
    required this.wsBase,
    required this.apiFromDartDefine,
    required this.apiOverriddenAtRuntime,
  });
}

class ConfigValidation {
  final bool ok;
  final String apiBase;
  final int? statusCode;
  final String? body;
  final String? error;
  const ConfigValidation({
    required this.ok,
    required this.apiBase,
    this.statusCode,
    this.body,
    this.error,
  });
  Map<String, dynamic> toJson() => {
        'ok': ok,
        'api_base': apiBase,
        if (statusCode != null) 'status_code': statusCode,
        if (body != null) 'body': body,
        if (error != null) 'error': error,
      };
  @override
  String toString() => jsonEncode(toJson());
}
