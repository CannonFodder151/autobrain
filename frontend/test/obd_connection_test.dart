import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/services/obd/elm327.dart';
import 'package:autobrain/services/obd/obd_connection.dart';

void main() {
  const vinHex = '49 02 01 '
      '31 48 47 43 4D 38 32 36 33 33 41 30 30 34 33 35 32'; // 1HGCM82633A004352

  group('updateVin', () {
    test('reads the VIN from the adapter and saves it exactly once', () async {
      final session = Elm327Session(FakeElmTransport({'0902': '$vinHex\r'}));
      final saved = <String>[];
      final vin = await updateVin(session, (v) async => saved.add(v));
      expect(vin, '1HGCM82633A004352');
      expect(saved, ['1HGCM82633A004352']);
    });

    test('throws when no adapter is connected', () async {
      await expectLater(updateVin(null, (_) async {}), throwsStateError);
    });

    test('never saves when the adapter cannot read the VIN', () async {
      final session = Elm327Session(FakeElmTransport({'0902': '?\r'}));
      var saved = 0;
      await expectLater(
          updateVin(session, (_) async => saved++),
          throwsA(isA<Elm327Exception>()));
      expect(saved, 0);
    });
  });
}
