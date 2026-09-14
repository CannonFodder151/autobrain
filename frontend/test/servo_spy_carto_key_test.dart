// Regression guard for AUT-2383: the CARTO basemap URL must use the
// `?key=` query parameter. The old `?api_key=` was silently ignored by
// CARTO, so tiles rendered with the "API key required" watermark even
// when the key was injected via --dart-define=CARTO_API_KEY.

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
}
