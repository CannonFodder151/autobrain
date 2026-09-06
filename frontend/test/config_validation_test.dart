import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:autobrain/core/config.dart';

void main() {
  setUp(() {
    // Per-test isolation: AppConfig.* are static, and previous tests can
    // mutate apiBase / lastValidationOk / lastValidationError. Reset before
    // each test so order doesn't matter. (AUT-2284 S3.)
    AppConfig.apiBase = 'https://example.test/api/v1';
    AppConfig.lastValidationOk = null;
    AppConfig.lastValidationError = null;
  });

  group('AppConfig.validate', () {
    test('2xx response marks the API base as reachable', () async {
      final client = MockClient((req) async {
        expect(req.url.path, '/healthz');
        expect(req.url.host, 'example.test');
        return http.Response('ok', 200);
      });
      await AppConfig.validate(client: client);
      expect(AppConfig.lastValidationOk, isTrue);
      expect(AppConfig.lastValidationError, isNull);
    });

    test('5xx response marks the API base as unreachable', () async {
      final client = MockClient(
        (req) async => http.Response('boom', 503),
      );
      await AppConfig.validate(client: client);
      expect(AppConfig.lastValidationOk, isFalse);
      expect(AppConfig.lastValidationError, contains('503'));
    });

    test('timeout marks the API base as unreachable', () async {
      final client = MockClient((req) async {
        // Never resolves — validator must enforce its own timeout.
        await Future<void>.delayed(const Duration(seconds: 30));
        return http.Response('ok', 200);
      });
      await AppConfig.validate(
        client: client,
        timeout: const Duration(milliseconds: 50),
      );
      expect(AppConfig.lastValidationOk, isFalse);
      expect(AppConfig.lastValidationError, contains('timeout'));
    });

    test('connection refused (plain Exception) marks unreachable', () async {
      // No SocketExceptionLike shim: http's MockClient throws plain Exception
      // here, and the validator's `catch (e)` doesn't care which subtype —
      // any thrown object works. (AUT-2284 S2.)
      final client = MockClient(
        (req) async => throw Exception('connection refused'),
      );
      await AppConfig.validate(client: client);
      expect(AppConfig.lastValidationOk, isFalse);
      expect(AppConfig.lastValidationError, contains('connection refused'));
    });

    test('malformed apiBase marks unreachable without hitting network',
        () async {
      AppConfig.apiBase = 'not a url';
      var calls = 0;
      final client = MockClient((req) async {
        calls += 1;
        return http.Response('ok', 200);
      });
      await AppConfig.validate(client: client);
      expect(calls, 0, reason: 'must short-circuit before issuing a request');
      expect(AppConfig.lastValidationOk, isFalse);
      expect(AppConfig.lastValidationError, contains('not a valid URL'));
    });
  });
}
