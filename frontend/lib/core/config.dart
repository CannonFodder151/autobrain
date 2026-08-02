/// Compile-time configuration.
///
/// Overridden at build time via --dart-define.
class AppConfig {
  static const String apiBase = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
  static const String wsBase = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'ws://localhost:8000/ws',
  );
}
