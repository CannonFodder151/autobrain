import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:autobrain/core/config.dart';

void main() {
  group('AppConfig.validate', () {
    tearDown(() {
      AppConfig.apiBase = 'https://localhost:8000/api/v1';
      AppConfig.wsBase = 'wss://localhost:8000/ws';
      AppConfig.lastValidationError = null;
      AppConfig.validated = false;
    });

    test('passes when /openapi.json returns 200', () async {
      AppConfig.apiBase = 'https://api.example.com/api/v1';
      final client = MockClient((req) async {
        expect(req.url.path, '/api/v1/openapi.json');
        return http.Response(jsonEncode({'openapi': '3.0.0'}), 200,
            headers: {'content-type': 'application/json'});
      });
      final ok = await AppConfig.validate(client: client);
      expect(ok, isTrue);
      expect(AppConfig.validated, isTrue);
      expect(AppConfig.lastValidationError, isNull);
    });

    test('treats 404 on openapi.json as proof the backend is up', () async {
      AppConfig.apiBase = 'https://api.example.com/api/v1';
      var calls = 0;
      final client = MockClient((req) async {
        calls++;
        if (req.url.path == '/api/v1/openapi.json') {
          // 404 means the host answered — no fallback needed.
          return http.Response('not found', 404);
        }
        return http.Response('no', 500);
      });
      final ok = await AppConfig.validate(client: client);
      expect(ok, isTrue);
      expect(calls, 1);
    });

    test('falls back to /health only on transport failure (connection refused)', () async {
      AppConfig.apiBase = 'https://api.example.com/api/v1';
      var calls = 0;
      final client = MockClient((req) async {
        calls++;
        if (req.url.path == '/api/v1/openapi.json') {
          throw const SocketExceptionShim('connection refused');
        }
        if (req.url.path == '/api/v1/health') {
          return http.Response(jsonEncode({'status': 'ok'}), 200);
        }
        return http.Response('no', 500);
      });
      final ok = await AppConfig.validate(client: client);
      expect(ok, isTrue);
      expect(calls, 2);
    });

    test('falls back to origin when /health 404s', () async {
      AppConfig.apiBase = 'https://api.example.com/api/v1';
      var calls = 0;
      final client = MockClient((req) async {
        calls++;
        if (req.url.path == '/' || req.url.path == '') {
          return http.Response('<html>hi</html>', 200);
        }
        return http.Response('no', 500);
      });
      final ok = await AppConfig.validate(client: client);
      expect(ok, isTrue);
      expect(calls, greaterThanOrEqualTo(1));
    });

    test('treats 3xx/4xx as proof of reachability', () async {
      AppConfig.apiBase = 'https://api.example.com/api/v1';
      final client = MockClient((req) async {
        return http.Response('redirect', 302);
      });
      final ok = await AppConfig.validate(client: client);
      expect(ok, isTrue);
    });

    test('fails when nothing answers and captures the URL', () async {
      AppConfig.apiBase = 'https://dead.example.com/api/v1';
      final client = MockClient((req) async {
        throw const SocketExceptionShim('connection refused');
      });
      final ok = await AppConfig.validate(client: client);
      expect(ok, isFalse);
      expect(AppConfig.validated, isFalse);
      expect(AppConfig.lastValidationError, contains('https://dead.example.com/api/v1'));
      expect(AppConfig.lastValidationError, contains('openapi.json'));
    });

    test('fails fast on malformed URL', () async {
      AppConfig.apiBase = 'not a url';
      final client = MockClient((req) async => http.Response('', 200));
      final ok = await AppConfig.validate(client: client);
      expect(ok, isFalse);
      expect(AppConfig.lastValidationError, contains('not a valid absolute URL'));
    });
  });
}

// Lightweight shim so the test doesn't import dart:io directly (Flutter web
// test runner cannot resolve dart:io).
class SocketExceptionShim implements Exception {
  const SocketExceptionShim(this.message);
  final String message;
  @override
  String toString() => 'SocketExceptionShim: $message';
}