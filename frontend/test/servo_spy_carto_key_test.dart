// Regression guard for AUT-2383 / AUT-4736: the CARTO basemap URL must use
// the `?key=` query parameter (the legacy `?api_key=` is silently ignored by
// CARTO, leaving the "API key required" watermark) AND the tile urlTemplate
// must actually interpolate the key param -- declaring it without using it
// fails silently (AUT-4736).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/screens/servo_spy/servo_spy_screen.dart';

void main() {
  group('cartoKeyParam (AUT-2383)', () {
    test('empty key produces no query string', () {
      expect(cartoKeyParam(''), '');
    });

    test('non-empty key uses ?key= (CARTO raster basemap parameter)', () {
      expect(cartoKeyParam('cb1_2tpq_1_af002c1a02641caa77f65c21'),
          '?key=cb1_2tpq_1_af002c1a02641caa77f65c21');
    });

    test('does NOT use the legacy ?api_key= (silent-watermark bug)', () {
      final out = cartoKeyParam('abc');
      expect(out, isNot(contains('api_key')),
          reason: 'CARTO ignores ?api_key= and shows the watermark');
      expect(out, contains('?key='));
    });
  });

  group('tile urlTemplate wiring (AUT-4736)', () {
    late String source;

    setUpAll(() {
      source = File('lib/screens/servo_spy/servo_spy_screen.dart').readAsStringSync();
    });

    test('both dark and light urlTemplates interpolate _kCartoKeyParam', () {
      final templates = RegExp(r"'https://\{s\}\.basemaps\.cartocdn\.com/[^']+'")
          .allMatches(source)
          .map((m) => m.group(0)!)
          .toList();
      expect(templates, hasLength(2));
      for (final t in templates) {
        expect(t, contains(r'${_kCartoKeyParam}'),
            reason: 'urlTemplate without the key param renders watermapped '
                'tiles even when CARTO_API_KEY is injected at build time');
      }
    });
  });
}