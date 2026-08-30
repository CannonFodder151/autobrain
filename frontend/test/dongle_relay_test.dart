// Unit tests for the BLE trip relay (AUT-1573): the CSV -> device-trip JSON
// conversion must mirror the firmware's upload_payload.h rules exactly so
// phone-relayed and WiFi-uploaded copies of one trip dedupe server-side.

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/services/dongle/dongle_relay.dart';

void main() {
  const csv = 'epoch,rpm,speed,coolant,throttle,lat,lon\n'
      '1767200400,826,75,44,50,0,0\n' // no fix -> dropped
      '1767200401,830,76,44,51,-338687241,1512109053\n'
      '1767200402,840,78,45,52,-338687250,1512109060\n'
      'junk-rows-are-skipped\n'
      '1767200403,850,80,45,53,0,0\n';

  test('converts a board trip CSV to the firmware-identical JSON shape', () {
    final obj = tripCsvToJson('20260801_090000.csv', csv);
    expect(obj, isNotNull);
    expect(obj!['device_trip_id'], 'trip_20260801_090000');
    expect(obj['started_at'], '2025-12-31T17:00:00.000Z');
    expect(obj['ended_at'], '2025-12-31T17:00:03.000Z');
    final samples = obj['gps_samples'] as List?;
    expect(samples, isNotNull);
    expect(samples!.length, 2); // the two rows with a GPS fix
    expect(
        samples[0], {'t': 1767200401, 'lat': -33.8687241, 'lon': 151.2109053});
  });

  test('returns null for CSVs without usable epoch rows', () {
    expect(tripCsvToJson('20260801_090000.csv', 'epoch,rpm,speed\n'), isNull);
    expect(tripCsvToJson('index.txt', csv), isNull); // non-trip file
    final empty = tripCsvToJson(
        '20260801_090000.csv', 'epoch,rpm,speed,coolant,throttle,lat,lon\n');
    expect(empty, isNull); // zero rows -> no start/end -> not uploadable
  });

  test('drops malformed lat/lon instead of throwing', () {
    const weird = 'epoch,rpm,speed,coolant,throttle,lat,lon\n'
        '1000,1,2,3,4,x,y\n'
        '1001,1,2,3,4,-338687241,1512109053\n';
    final obj = tripCsvToJson('20260801_090000.csv', weird)!;
    expect((obj['gps_samples'] as List).length, 1);
  });
}
