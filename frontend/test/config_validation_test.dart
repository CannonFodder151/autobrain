import 'package:autobrain/core/config.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// AUT-2192: assert AppConfig.validate() correctly classifies reachable and
/// unreachable BACKEND_URLs at app boot. Single source of truth is the
/// compiled `API_BASE_URL`; the probe must hit `${origin}/healthz` and
/// surface failures via AppConfig.lastValidationError.
void main() {
  setUp(() {
    AppConfig.lastValidationOk = null;
    AppConfig.lastValidationError = null;
  });

  test('validate() marks reachable 2xx as ok', () async {
    final client = MockClient((req) async {
      expect(req.url.path, '/healthz');
      return http.Response('{"ok":true}', 200);
    });
    AppConfig.apiBase = 'https://api.example.com/api/v1';
    await AppConfig.validate(client: client);
    expect(AppConfig.lastValidationOk, isTrue);
    expect(AppConfig.lastValidationError, isNull);
  });

  test('validate() marks 5xx as failure with status in error', () async {
    final client = MockClient((req) async => http.Response('boom', 503));
    AppConfig.apiBase = 'https://api.example.com/api/v1';
    await AppConfig.validate(client: client);
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('503'));
  });

  test('validate() surfaces timeout as failure', () async {
    final client = MockClient((req) async {
      await Future<void>.delayed(const Duration(seconds: 30));
      return http.Response('never', 200);
    });
    AppConfig.apiBase = 'https://api.example.com/api/v1';
    await AppConfig.validate(
      client: client,
      timeout: const Duration(milliseconds: 50),
    );
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('timeout'));
  });

  test('validate() surfaces connection error as failure', () async {
    final client = MockClient((req) async {
      throw const SocketExceptionLike('connection refused');
    });
    AppConfig.apiBase = 'https://api.example.com/api/v1';
    await AppConfig.validate(client: client);
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('refused'));
  });

  test('validate() flags malformed apiBase as failure', () async {
    AppConfig.apiBase = 'not a url';
    await AppConfig.validate(client: MockClient((_) async => http.Response('', 200)));
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('not a valid URL'));
  });
}

/// Local stand-in for dart:io SocketException so this test does not pull in
/// dart:io (which would require running on the VM, not the browser test
/// runner). The mocked throw above is enough for the validator's
/// catch-all path.
class SocketExceptionLike implements Exception {
  final String message;
  const SocketExceptionLike(this.message);
  @override
  String toString() => 'SocketExceptionLike: $message';
}
