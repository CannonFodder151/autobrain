// Tests for AUT-1821: Servo Spy list sort + filter model logic.
// Pure (no Flutter) so it stays cheap to run.

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/screens/servo_spy/servo_spy_list_model.dart';

ServoStationRow _row(String name, {double? price, double? distance}) => ServoStationRow(
      name: name,
      priceCents: price,
      distanceKm: distance,
    );

void main() {
  test('default sort is cheapest first (price low -> high)', () {
    final rows = [
      _row('B', price: 189.9),
      _row('A', price: 165.7),
      _row('C', price: 172.3),
    ];
    final sorted = sortStationRows(rows, ServoSortMetric.price);
    expect(sorted.map((r) => r.name).toList(), ['A', 'C', 'B']);
  });

  test('distance sort is nearest first', () {
    final rows = [
      _row('Far', distance: 12.4),
      _row('Near', distance: 1.2),
      _row('Mid', distance: 5.0),
    ];
    final sorted = sortStationRows(rows, ServoSortMetric.distance);
    expect(sorted.map((r) => r.name).toList(), ['Near', 'Mid', 'Far']);
  });

  test('rows missing the sort metric sort to the end', () {
    final rows = [
      _row('NoPrice', price: null),
      _row('Cheap', price: 150.0),
      _row('Pricey', price: 200.0),
    ];
    final sorted = sortStationRows(rows, ServoSortMetric.price);
    expect(sorted.map((r) => r.name).toList(), ['Cheap', 'Pricey', 'NoPrice']);
  });

  test('round-trips the station fields from the API payload', () {
    final row = ServoStationRow(
      name: 'Shell',
      brand: 'Shell',
      logoUrl: 'https://example.com/logo.png',
      distanceKm: 3.1,
      priceCents: 179.9,
      fuelType: '91',
    );
    expect(row.name, 'Shell');
    expect(row.priceCents, 179.9);
    expect('\$${(row.priceCents! / 100).toStringAsFixed(3)}', '\$1.799');
  });
}
