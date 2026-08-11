import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/trip_datetime.dart';

void main() {
  DateTime dt(DateTime d, int h, int m) => DateTime(d.year, d.month, d.day, h, m);
  final aug11 = DateTime(2026, 8, 11);

  test('accepts ISO input (regression)', () {
    expect(parseLogbookDateTime('2026-08-11', '15:30'), dt(aug11, 15, 30));
    expect(parseLogbookDateTime('2026-08-11', ''), dt(aug11, 0, 0));
  });

  test('accepts Australian d/M/y with 12h time (reported bug)', () {
    expect(parseLogbookDateTime('11/08/2026', '3:30 PM'), dt(aug11, 15, 30));
    expect(parseLogbookDateTime('11/08/2026', '3:30pm'), dt(aug11, 15, 30));
    expect(parseLogbookDateTime('11/8/2026', '9:05 am'), dt(aug11, 9, 5));
  });

  test('accepts dash and dot date separators', () {
    expect(parseLogbookDateTime('11-08-2026', '15:30'), dt(aug11, 15, 30));
    expect(parseLogbookDateTime('11.08.2026', '15:30'), dt(aug11, 15, 30));
  });

  test('accepts month-name dates', () {
    expect(parseLogbookDateTime('11 Aug 2026', '15:30'), dt(aug11, 15, 30));
    expect(parseLogbookDateTime('11 August 2026', '15:30'), dt(aug11, 15, 30));
  });

  test('handles midnight/noon and compact 24h times', () {
    expect(parseLogbookDateTime('11/08/2026', '12:00 am'), dt(aug11, 0, 0));
    expect(parseLogbookDateTime('11/08/2026', '12:00 pm'), dt(aug11, 12, 0));
    expect(parseLogbookDateTime('11/08/2026', '1530'), dt(aug11, 15, 30));
  });

  test('rejects genuinely invalid input', () {
    expect(parseLogbookDateTime('', '15:30'), isNull);
    expect(parseLogbookDateTime('32/13/2026', '15:30'), isNull);
    expect(parseLogbookDateTime('11/08/2026', '25:99'), isNull);
    expect(parseLogbookDateTime('garbage', '15:30'), isNull);
  });
}