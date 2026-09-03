// AUT-2192 — integration test that the resolved BACKEND_URL/API_BASE is
// reachable at app boot via the AppConfig.validate() probe. Spins a local
// HttpServer bound to loopback so the test is hermetic; mirrors the pattern
// in api_client_upload_test.dart. Also covers the malformed-URL fail-fast.

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/config.dart';

void main() {
  group('AppConfig.validate (AUT-2192)', () {
    setUp(() {
      // Reset static config so prior tests don't leak into this one.
      AppConfig.apiBase = 'http://localhost/api/v1';
      AppConfig.wsBase = 'ws://localhost/ws';
      AppConfig.lastValidation = null;
    });

    test('reachable /health returns ok with status + body snapshot', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((req) async {
        if (req.uri.path == '/health') {
          req.response.statusCode = 200;
          req.response.headers.contentType = ContentType.json;
          req.response.write('{"status":"ok"}');
        } else {
          req.response.statusCode = 404;
        }
        await req.response.close();
      });
      addTearDown(() => server.close(force: true));

      AppConfig.apiBase = 'http://${server.address.host}:${server.port}/api/v1';
      final v = await AppConfig.validate();
      expect(v.ok, isTrue, reason: v.error);
      expect(v.apiBase, AppConfig.apiBase);
      expect(v.statusCode, 200);
      expect(v.body, contains('status'));
      expect(AppConfig.lastValidation?.ok, isTrue);
    });

    test('5xx response surfaces as validation failure with status', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((req) async {
        req.response.statusCode = 503;
        await req.response.close();
      });
      addTearDown(() => server.close(force: true));

      AppConfig.apiBase = 'http://${server.address.host}:${server.port}/api/v1';
      final v = await AppConfig.validate();
      expect(v.ok, isFalse);
      expect(v.statusCode, 503);
      expect(v.error, contains('503'));
    });

    test('closed port fails fast with a connection error', () async {
      // bind+immediately-close so the OS releases the port; probe will fail
      // with a socket error rather than a TimeoutException. Either outcome is
      // a validation failure — that is what we assert.
      final probe = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final deadHost = probe.address.host;
      final deadPort = probe.port;
      await probe.close(force: true);

      AppConfig.apiBase = 'http://$deadHost:$deadPort/api/v1';
      final v = await AppConfig.validate();
      expect(v.ok, isFalse);
      expect(v.error, isNotNull);
    });

    test('non-routable host times out and surfaces TimeoutException', () async {
      // RFC 5737 TEST-NET-1: guaranteed not to be in any local routing table.
      // The probe will hit the _probeTimeout (4s) and report a timeout.
      AppConfig.apiBase = 'http://192.0.2.1:1/api/v1';
      final v = await AppConfig.validate();
      expect(v.ok, isFalse);
      expect(v.error, contains('timed out'));
    });

    test('host-less URL fails fast without a network call', () async {
      // Uri.parse is permissive; "not a url" parses without throwing but the
      // host is empty so validate() rejects it before any HTTP call.
      AppConfig.apiBase = 'not a url';
      final v = await AppConfig.validate();
      expect(v.ok, isFalse);
      expect(v.error, contains('no host'));
    });

    test('describe() reports dart-define vs runtime override', () {
      // _defaultApiBase is the compiled --dart-define value. apiBase is set
      // by AppConfig.load() (web/desktop) or by the server picker (mobile).
      // We can't reliably flip dart-define from a unit test, so we only
      // assert the fields exist and round-trip.
      final d = AppConfig.describe();
      expect(d.apiBase, AppConfig.apiBase);
      expect(d.wsBase, AppConfig.wsBase);
      expect(d.apiFromDartDefine, isA<bool>());
      expect(d.apiOverriddenAtRuntime, isA<bool>());
    });
  });
}
