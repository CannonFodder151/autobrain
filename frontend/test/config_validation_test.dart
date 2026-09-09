// AUT-2354: regression coverage for AppConfig.validate() — the boot-time
// reachability probe must classify all five failure modes we expect to see
// in the field, without ever throwing (the caller reads the static fields,
// not the Future's result).
//
// Uses package:http/testing.dart's MockClient so the test is hermetic — no
// real socket, no real DNS, runs in <100ms.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:autobrain/core/config.dart';

void _reset() {
  AppConfig.apiBase = 'https://example.test/api/v1';
  AppConfig.wsBase = 'wss://example.test/ws';
  AppConfig.lastValidationOk = null;
  AppConfig.lastValidationError = null;
}

void main() {
  setUp(_reset);

  test('2xx healthz -> ok', () async {
    final client = MockClient((req) async {
      expect(req.url.path, '/healthz');
      return http.Response('{"status":"ok"}', 200,
          headers: {'content-type': 'application/json'});
    });
    await AppConfig.validate(client: client, timeout: const Duration(seconds: 2));
    expect(AppConfig.lastValidationOk, isTrue);
    expect(AppConfig.lastValidationError, isNull);
  });

  test('5xx healthz -> fail with status code in error', () async {
    final client = MockClient((_) async => http.Response('boom', 503));
    await AppConfig.validate(client: client, timeout: const Duration(seconds: 2));
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('503'));
  });

  test('timeout -> fail with timeout in error', () async {
    final client = MockClient((_) async {
      await Future<void>.delayed(const Duration(seconds: 5));
      return http.Response('late', 200);
    });
    await AppConfig.validate(client: client, timeout: const Duration(milliseconds: 50));
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('timeout'));
  });

  test('connection refused -> fail with underlying error', () async {
    // MockClient can't simulate SocketException directly without a real
    // socket; we exercise the catch-all path by throwing from the handler.
    final client = MockClient((_) async {
      throw const SocketException('Connection refused');
    });
    await AppConfig.validate(client: client, timeout: const Duration(seconds: 2));
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('Connection refused'));
  });

  test('malformed apiBase -> fail with URL parse error, no HTTP call', () async {
    var called = false;
    final client = MockClient((_) async {
      called = true;
      return http.Response('', 200);
    });
    AppConfig.apiBase = 'not a url at all';
    await AppConfig.validate(client: client, timeout: const Duration(seconds: 2));
    expect(called, isFalse, reason: 'malformed URL must not reach the client');
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, contains('not a valid URL'));
  });

  test('empty apiBase -> fail without throwing', () async {
    final client = MockClient((_) async => http.Response('', 200));
    AppConfig.apiBase = '';
    await AppConfig.validate(client: client, timeout: const Duration(seconds: 2));
    expect(AppConfig.lastValidationOk, isFalse);
    expect(AppConfig.lastValidationError, isNotNull);
  });
}

// Suppress unused-import warning for dart:convert (retained for future
// JSON-asserting tests; current assertions are substring-based).
// ignore: unused_element
void _keepImports() {
  jsonEncode(<String, Object?>{});
}
