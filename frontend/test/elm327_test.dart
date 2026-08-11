import 'package:flutter_test/flutter_test.dart';
import 'package:autobrain/services/obd/elm327.dart';

void main() {
  group('normalizeReply', () {
    test('strips echo, prompt, CR and noise', () {
      final r = normalizeReply('ATZ\rELM327 v1.5\r\rOK\r>', 'ATZ');
      expect(r, ['ELM327 v1.5', 'OK']);
    });

    test('drops echoed command line', () {
      final r = normalizeReply('010C\r41 0C 1A F8\r\r>', '010C');
      expect(r, ['41 0C 1A F8']);
    });

    test('handles adapters that ignore AT S0 (spaces present)', () {
      final r = normalizeReply('41 0C 1A\tF8\r>', '010C');
      expect(r, ['41 0C 1A\tF8']);
    });
  });

  group('parseHexPayload', () {
    test('parses spaced hex', () {
      expect(parseHexPayload('41 0C 1A F8'), [0x41, 0x0C, 0x1A, 0xF8]);
    });
    test('parses compact hex', () {
      expect(parseHexPayload('410C1AF8'), [0x41, 0x0C, 0x1A, 0xF8]);
    });
    test('rejects odd length', () {
      expect(() => parseHexPayload('410'), throwsA(isA<Elm327Exception>()));
    });
  });

  group('PID decoding', () {
    test('engine RPM', () {
      final pid = livePids.firstWhere((p) => p.command == '010C');
      final b = mode01Payload('41 0C 1A F8', '0C');
      expect(pid.value(b), closeTo(1726, 0.5));
    });

    test('coolant temp offset', () {
      final pid = livePids.firstWhere((p) => p.command == '0105');
      expect(pid.value(mode01Payload('41 05 55', '05')), 45);
    });

    test('vehicle speed', () {
      final pid = livePids.firstWhere((p) => p.command == '010D');
      expect(pid.value(mode01Payload('41 0D 3C', '0D')), 60);
    });

    test('engine load percent', () {
      final pid = livePids.firstWhere((p) => p.command == '0104');
      expect(pid.value(mode01Payload('41 04 80', '04')), closeTo(50.2, 0.1));
    });

    test('label formatting', () {
      final pid = livePids.firstWhere((p) => p.command == '010C');
      final r = PidReading(pid, 1726);
      expect(r.label, 'Engine RPM: 1726 rpm');
    });
  });

  group('DTC decoding', () {
    test('powertrain code', () {
      expect(decodeDtc(0x01, 0x01), 'P0101');
      expect(decodeDtc(0x01, 0x00), 'P0100');
    });
    test('body code from high category bits', () {
      expect(decodeDtc(0x81, 0x01), 'B0101');
    });
    test('mode 03 reply (count byte then DTC pairs)', () {
      expect(decodeDtcReply(['43 01 01 01 00 00'], 3), ['P0101']);
    });
    test('mode 07 pending reply multi-DTC', () {
      expect(
        decodeDtcReply(['47 01 02 01 01 00'], 7),
        ['P0201', 'P0100'],
      );
    });
    test('known-code description lookup', () {
      expect(dtcDescription('P0301'), 'Cylinder 1 misfire');
      expect(dtcDescription('U9999'), isNull);
    });
  });

  group('VIN decoding', () {
    test('strips 49 02 01 prefix and decodes ASCII', () {
      // "1HGCM82633A004352" (17 chars)
      const vin = '1HGCM82633A004352';
      final hex = vin
          .codeUnits
          .map((c) => c.toRadixString(16).padLeft(2, '0'))
          .join(' ');
      final lines = ['49 02 01 $hex'];
      expect(decodeVin(lines), vin);
    });
    test('throws on non-VIN reply', () {
      expect(() => decodeVin(['43 01 01']), throwsA(isA<Elm327Exception>()));
    });
  });

  group('supported PIDs', () {
    test('BE 1F B8 11 maps to known PIDs', () {
      final set = decodeSupportedPids({'0100': ['41 00 BE 1F B8 11']});
      expect(set.contains('0101'), isTrue);
      expect(set.contains('0102'), isFalse);
      expect(set.contains('010C'), isTrue);
      expect(set.contains('0113'), isTrue);
      expect(set.contains('011B'), isFalse);
    });
  });

  group('Elm327Session with scripted adapter', () {
    const vinHex = '49 02 01 '
        '31 48 47 43 4D 38 32 36 33 33 41 30 30 34 33 35 32'; // 1HGCM82633A004352
    final script = {
      'ATZ': 'ELM327 v1.5\rOK\r',
      'ATE0': 'OK\r',
      'ATH0': 'OK\r',
      'ATL0': 'OK\r',
      'ATS0': 'OK\r',
      'ATSP0': 'OK\r',
      '0902': '$vinHex\r',
      '03': '43 01 01 01 00 00\r',
      '07': '47 01 02 01 01 00\r',
      '0100': '41 00 BE 1F B8 11\r',
      '0120': '41 20 00 00 00 00\r',
      '0140': '41 40 00 00 00 00\r',
      '0160': '41 60 00 00 00 00\r',
      '0180': '41 80 00 00 00 00\r',
      '01A0': '41 A0 00 00 00 00\r',
      '01C0': '41 C0 00 00 00 00\r',
      '0104': '41 04 80\r',
      '0105': '41 05 55\r',
      '010C': '41 0C 1A F8\r',
      '010D': '41 0D 3C\r',
      '010F': '41 0F 55\r',
      '0110': '41 10 01 6B\r',
    };

    test('init + readVin + readDtc + readPid', () async {
      final session = Elm327Session(FakeElmTransport(script));
      await session.init();
      expect(await session.readVin(), '1HGCM82633A004352');
      final dtcs = await session.readDtc();
      expect(dtcs.map((d) => d.code).toList(), ['P0101', 'P0201', 'P0100']);
      final rpm = await session.readPid(
          livePids.firstWhere((p) => p.command == '010C'));
      expect(rpm!.value, closeTo(1726, 0.5));
      final supported = await session.readSupportedPids();
      expect(supported.contains('010C'), isTrue);
      expect(supported.contains('0102'), isFalse);
    });

    test('readLive skips unsupported PIDs', () async {
      final session = Elm327Session(FakeElmTransport(script));
      final readings = await session.readLive(
          supported: await session.readSupportedPids());
      expect(readings.map((r) => r.pid.command),
          containsAll(['0104', '0105', '010C', '010D']));
    });

    test('reports unsupported command via adapter rejection', () async {
      final t = FakeElmTransport({...script, '010C': '?\r'});
      final session = Elm327Session(t);
      await session.init();
      expect(() => session.readPid(livePids[2]),
          throwsA(isA<Elm327Exception>()));
    });
  });
}
