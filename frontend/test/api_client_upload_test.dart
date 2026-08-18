// Regression test for AUT-796: Community Garage photo upload must not crash on
// empty/unparseable content types (the empty string `XFile.mimeType` returns
// for HEIC). `upload` sanitizes and falls back to a filename-derived MIME.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/config.dart';

void main() {
  test('safeContentType falls back for empty/whitespace/garbage (AUT-796)',
      () {
    expect(safeContentType('', 'photo.jpg').toString(), 'image/jpeg');
    expect(safeContentType('   ', 'photo.png').toString(), 'image/png');
    expect(safeContentType('not-a-valid-mime', 'scan.pdf').toString(),
        'application/pdf');
    expect(safeContentType('', 'unknown.bin').toString(),
        'application/octet-stream');
    expect(safeContentType('image/webp', 'photo.jpg').toString(), 'image/webp');
  });

  test('upload with empty content type does not throw and sends fallback',
      () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    String? receivedBody;
    server.listen((req) async {
      receivedBody = utf8.decode(
        await req.fold<List<int>>([], (acc, c) => [...acc, ...c]),
        allowMalformed: true,
      );
      req.response.statusCode = 200;
      req.response.write('{}');
      await req.response.close();
    });
    addTearDown(() => server.close(force: true));

    AppConfig.apiBase = 'http://${server.address.host}:${server.port}/api/v1';
    final api = ApiClient(null);
    final result =
        await api.upload('/social/posts/b1/photo', [1, 2, 3], 'photo.jpg', '');
    expect(result, isA<Map>());
    expect(receivedBody!.toLowerCase(), contains('content-type: image/jpeg'));
  });
}
