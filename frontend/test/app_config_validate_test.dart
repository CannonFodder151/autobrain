import 'package:autobrain/core/config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    AppConfig.apiBase = 'http://localhost:8000/api/v1';
    AppConfig.wsBase = 'ws://localhost:8000/ws';
    AppConfig.lastValidationOk = false;
    AppConfig.lastValidationError = null;
  });

  test('validate() with unreachable backend reports failure', () async {
    AppConfig.apiBase = 'http://127.0.0.1:1/api/v1';
    await AppConfig.validate(timeout: const Duration(milliseconds: 200));
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, isNotNull);
  });

  test('healthz origin strips /api/v1 suffix', () {
    AppConfig.apiBase = 'https://example.com/api/v1';
    final origin = AppConfig.apiBase.replaceFirst(RegExp(r'/api/v1/?$'), '');
    expect(origin, 'https://example.com');
  });
}
