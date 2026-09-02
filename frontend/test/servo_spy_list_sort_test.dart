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

// AUT-2070: list view previously always took prices[0], ignoring the
  // selected fuel type. The parser now picks the matching entry and falls
  // back to the first available price when the selected fuel is absent.
  test('pickPriceForFuel selects the entry matching the selected fuel type', () {
    final prices = [
      {'fuel_type': 'E10', 'price': 165.7},
      {'fuel_type': '91', 'price': 178.9},
      {'fuel_type': 'Diesel', 'price': 189.0},
    ];
    final p = pickPriceForFuel(prices, '91');
    expect(p.priceCents, 178.9);
    expect(p.fuelType, '91');
  });

  test('pickPriceForFuel falls back to first price when selected fuel is missing', () {
    final prices = [
      {'fuel_type': '91', 'price': 178.9},
      {'fuel_type': 'Diesel', 'price': 189.0},
    ];
    final p = pickPriceForFuel(prices, 'LPG');
    expect(p.priceCents, 178.9);
    expect(p.fuelType, '91');
  });

  test('pickPriceForFuel returns nulls on an empty payload', () {
    final p = pickPriceForFuel(const [], '91');
    expect(p.priceCents, isNull);
    expect(p.fuelType, isNull);
  });

  test('stationRowFromApi fills name + distance and the right price', () {
    final row = stationRowFromApi(
      {
        'name': 'BP Cluden',
        'brand': 'BP',
        'logo': 'https://example.com/bp.png',
        'distance_km': 2.4,
        'prices': [
          {'fuel_type': 'E10', 'price': 165.7},
          {'fuel_type': '95', 'price': 184.0},
        ],
      },
      selectedFuelType: '95',
    );
    expect(row.name, 'BP Cluden');
    expect(row.brand, 'BP');
    expect(row.distanceKm, 2.4);
    expect(row.priceCents, 184.0);
    expect(row.fuelType, '95');
  });

  test('pickPriceForFuel with null selectedFuelType picks the first available entry', () {
    final prices = [
      {'fuel_type': '91', 'price': 178.9},
      {'fuel_type': 'Diesel', 'price': 189.0},
    ];
    final p = pickPriceForFuel(prices, null);
    expect(p.priceCents, 178.9);
    expect(p.fuelType, '91');
  });

  test('pickPriceForFuel skips malformed entries and picks the first valid one', () {
    final prices = [
      'not a map',
      {'fuel_type': null, 'price': '0'},
      {'fuel_type': '91', 'price': 178.9},
    ];
    final p = pickPriceForFuel(prices, '91');
    expect(p.priceCents, 178.9);
    expect(p.fuelType, '91');
  });

  test('pickPriceForFuel parses string price (e.g. "178.9") as double', () {
    final prices = [
      {'fuel_type': '91', 'price': '178.9'},
    ];
    final p = pickPriceForFuel(prices, '91');
    expect(p.priceCents, 178.9);
  });

  test('stationRowFromApi with no selectedFuelType picks the first price', () {
    final row = stationRowFromApi(
      {
        'name': 'Caltex',
        'brand': 'Caltex',
        'distance_km': 1.0,
        'prices': [
          {'fuel_type': 'E10', 'price': 165.7},
          {'fuel_type': '95', 'price': 184.0},
        ],
      },
    );
    expect(row.priceCents, 165.7);
    expect(row.fuelType, 'E10');
  });

  test('stationRowFromApi with no prices key still returns a row with null price', () {
    final row = stationRowFromApi(
      {
        'name': 'No Prices',
        'brand': 'Unknown',
        'distance_km': 3.0,
      },
      selectedFuelType: '91',
    );
    expect(row.name, 'No Prices');
    expect(row.priceCents, isNull);
    expect(row.fuelType, isNull);
  });
}
