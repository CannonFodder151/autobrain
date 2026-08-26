// Unit tests for the dongle provisioning payload builder + device API
// (AUT-936). The payload must stay compact with keys in the firmware's exact
// order — the esp32-diy board has no JSON parser and extracts "key":"value"
// substrings.

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/services/dongle/dongle_api.dart';
import 'package:autobrain/services/dongle/dongle_provisioning.dart';

void main() {
  group('buildProvisioningPayload', () {
    test('emits compact JSON with keys in firmware order', () {
      final payload = buildProvisioningPayload(
        ssid: 'HomeSSID',
        pass: 'wifi-password',
        deviceId: 'dev-1',
        apiKey: 'abdev_abc123',
      );
      expect(
        payload,
        '{"ssid":"HomeSSID","pass":"wifi-password","device_id":"dev-1",'
        '"api_key":"abdev_abc123"}',
      );
      // No whitespace anywhere (the firmware substring-parses the payload).
      expect(payload, isNot(contains(' ')));
    });

    test('omits api_url when null or empty (firmware defaults to hosted)', () {
      expect(
        buildProvisioningPayload(
          ssid: 'S',
          pass: 'P',
          deviceId: 'd',
          apiKey: 'k',
        ),
        isNot(contains('api_url')),
      );
      expect(
        buildProvisioningPayload(
          ssid: 'S',
          pass: 'P',
          deviceId: 'd',
          apiKey: 'k',
          apiUrl: '',
        ),
        isNot(contains('api_url')),
      );
    });

    test('inserts api_url for self-hosted users between pass and device_id',
        () {
      final payload = buildProvisioningPayload(
        ssid: 'S',
        pass: 'P',
        deviceId: 'd',
        apiKey: 'k',
        apiUrl: 'https://my.host/api/v1',
      );
      expect(
        payload,
        '{"ssid":"S","pass":"P","api_url":"https://my.host/api/v1",'
        '"device_id":"d","api_key":"k"}',
      );
    });

    test('escapes quotes and backslashes so substring parsing cannot break',
        () {
      final payload = buildProvisioningPayload(
        ssid: 'Net"5',
        pass: r'p\a"ss',
        deviceId: 'd',
        apiKey: 'k',
      );
      expect(payload, contains(r'"ssid":"Net\"5"'));
      expect(payload, contains(r'"pass":"p\\a\"ss"'));
      expect(payload, isNot(contains(r'"pass":"p\a"ss"')),
          reason: 'raw pass must not appear unescaped');
    });
  });

  group('appendProvisionToken (AUT-969 F2)', () {
    test('appends prov_token before the closing brace', () {
      final payload = buildProvisioningPayload(
        ssid: 'Home',
        pass: 'wifi-password',
        deviceId: 'dev-1',
        apiKey: 'abdev_abc123',
      );
      final withToken = appendProvisionToken(payload, '0123456789abcdef');
      expect(
        withToken,
        '{"ssid":"Home","pass":"wifi-password","device_id":"dev-1",'
        '"api_key":"abdev_abc123","prov_token":"0123456789abcdef"}',
      );
      expect(withToken, isNot(contains(' ')));
    });

    test('keeps payload unchanged when no token (older firmware/boards)', () {
      final payload = buildProvisioningPayload(
        ssid: 'S',
        pass: 'P',
        deviceId: 'd',
        apiKey: 'k',
      );
      expect(appendProvisionToken(payload, null), payload);
      expect(appendProvisionToken(payload, ''), payload);
    });

    test('firmware can extract prov_token from any position', () {
      final payload = appendProvisionToken(
        '{"ssid":"S","pass":"P","device_id":"d","api_key":"k"}',
        'a1b2c3d4e5f60718',
      );
      // The on-device extractor searches each key independently.
      expect(payload, contains('"prov_token":"a1b2c3d4e5f60718"'));
    });
  });

  group('validateWifiInput (AUT-963 F3)', () {
    test('accepts boundary sizes (ssid 1–32, pass 8–63)', () {
      expect(validateWifiInput(ssid: 'A' * 32, pass: '12345678'), isNull);
      expect(validateWifiInput(ssid: 'A' * 32, pass: 'x' * 63), isNull);
      expect(validateWifiInput(ssid: 'A', pass: '12345678'), isNull);
    });

    test('rejects empty or oversize ssid', () {
      expect(validateWifiInput(ssid: '', pass: '12345678'), isNotNull);
      expect(validateWifiInput(ssid: 'A' * 33, pass: '12345678'),
          contains('SSID'));
    });

    test('rejects short or oversize pass', () {
      expect(validateWifiInput(ssid: 'Home', pass: '1234567'),
          contains('at least 8'));
      expect(validateWifiInput(ssid: 'Home', pass: 'x' * 64), contains('63'));
    });

    test('counts octets, not characters, for non-ASCII input', () {
      expect(validateWifiInput(ssid: 'é' * 33, pass: '12345678'),
          contains('SSID'));
    });

    test('rejects " or \\ in ssid/pass — firmware cannot unescape (AUT-968 F2)',
        () {
      expect(validateWifiInput(ssid: 'Net"5', pass: '12345678'),
          contains('" or \\'));
      expect(validateWifiInput(ssid: r'Net\5', pass: '12345678'), isNotNull);
      expect(validateWifiInput(ssid: 'Home', pass: 'pa"ssword1'), isNotNull);
      expect(validateWifiInput(ssid: 'Home', pass: r'p\assword1'), isNotNull);
    });
  });

  group('provisionAckMessage (AUT-969 F6)', () {
    test('maps first-write gate to a factory-reset hint (AUT-968 F5)', () {
      expect(
        provisionAckMessage('err:already configured'),
        contains('factory-reset'),
      );
    });

    test('maps token/expiry rejection to a re-pair hint (AUT-969 F6)', () {
      expect(
        provisionAckMessage('err:token missing or expired'),
        contains('Re-pair'),
      );
    });

    test('surfaces other err: verbatim without the prefix', () {
      expect(provisionAckMessage('err:need ssid,device_id,api_key'),
          'need ssid,device_id,api_key');
    });

    test('passes non-error acks through unchanged', () {
      expect(provisionAckMessage('ok'), 'ok');
    });
  });

  group('DongleApi', () {
    test('create posts name + vehicle_id and parses the one-time key',
        () async {
      final api = _FakeApi()
        ..response = {
          'id': 'dev-1',
          'name': 'AutoBrain-Tripper',
          'vehicle_id': 'v9',
          'api_key_prefix': 'abdev_abcd',
          'api_key': 'abdev_abcd1234',
          'last_seen_at': null,
          'created_at': '2026-08-16T10:00:00Z',
        };
      final dongle = DongleApi(api);
      final device = await dongle.create(
        name: 'AutoBrain-Tripper',
        vehicleId: 'v9',
      );
      expect(api.requests.single, 'POST /devices');
      expect(
          api.bodies.single, {'name': 'AutoBrain-Tripper', 'vehicle_id': 'v9'});
      expect(device.id, 'dev-1');
      expect(device.oneTimeApiKey, 'abdev_abcd1234');
      expect(device.vehicleId, 'v9');
    });

    test('create omits vehicle_id when none chosen', () async {
      final api = _FakeApi()
        ..response = {
          'id': 'dev-2',
          'name': 'Dongle',
          'vehicle_id': null,
          'api_key': 'abdev_x',
          'last_seen_at': null,
          'created_at': '2026-08-16T10:00:00Z',
        };
      final device = await DongleApi(api).create(name: 'Dongle');
      expect(api.bodies.single, {'name': 'Dongle'});
      expect(device.vehicleId, isNull);
    });

    test('list maps last_seen_at and never exposes a key', () async {
      final api = _FakeApi()
        ..response = [
          {
            'id': 'dev-1',
            'name': 'Dongle',
            'vehicle_id': 'v1',
            'api_key_prefix': 'abdev_abcd',
            'last_seen_at': '2026-08-15T22:30:00Z',
            'created_at': '2026-08-16T10:00:00Z',
          }
        ];
      final devices = await DongleApi(api).list();
      expect(api.requests.single, 'GET /devices');
      expect(devices.single.lastSeenAt, DateTime.utc(2026, 8, 15, 22, 30));
      expect(devices.single.oneTimeApiKey, isNull);
    });
  });
}

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  final requests = <String>[];
  final bodies = <Object?>[];
  Object? response;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) {
    requests.add('GET $path');
    return Future.value(response);
  }

  @override
  Future<dynamic> post(String path,
      [Object? body, Map<String, String>? headers]) {
    requests.add('POST $path');
    bodies.add(body);
    return Future.value(response);
  }
}
