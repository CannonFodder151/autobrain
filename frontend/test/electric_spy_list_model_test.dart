// Parser + sort tests for the Electric Spy list model (AUT-2435).
//
// Pure-Dart, no Flutter framework. Runs under `flutter test` in CI.

import 'package:autobrain/screens/electric_spy/electric_spy_list_model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('cheapestCostPerKwh', () {
    test('picks the lowest positive value', () {
      expect(cheapestCostPerKwh([null, 0.45, 0.39, 0.42]), 0.39);
      expect(cheapestCostPerKwh([0.42]), 0.42);
    });

    test('returns null when nothing usable', () {
      expect(cheapestCostPerKwh([]), isNull);
      expect(cheapestCostPerKwh([null, null]), isNull);
      expect(cheapestCostPerKwh([0.0, 0.0]), isNull);
    });
  });

  group('sortEvRows', () {
    List<EvStationRow> sample() => [
      EvStationRow(
        name: 'Cheap fast',
        distanceKm: 5.0,
        costPerKwh: 0.30,
        maxPowerKw: 50,
      ),
      EvStationRow(
        name: 'Expensive close',
        distanceKm: 1.0,
        costPerKwh: 0.65,
        maxPowerKw: 22,
      ),
      EvStationRow(
        name: 'Mid far',
        distanceKm: 30.0,
        costPerKwh: 0.45,
        maxPowerKw: 150,
      ),
    ];

    test('sorts by price ascending', () {
      final rows = sample();
      sortEvRows(rows, EvSortMetric.price);
      expect(rows.first.name, 'Cheap fast');
      expect(rows.last.name, 'Expensive close');
    });

    test('sorts by distance ascending', () {
      final rows = sample();
      sortEvRows(rows, EvSortMetric.distance);
      expect(rows.first.name, 'Expensive close');
      expect(rows.last.name, 'Mid far');
    });

    test('sorts by power descending', () {
      final rows = sample();
      sortEvRows(rows, EvSortMetric.power);
      expect(rows.first.name, 'Mid far');
      expect(rows.last.name, 'Expensive close');
    });

    test('rows missing the metric sort to the end', () {
      final rows = [
        EvStationRow(name: 'A', costPerKwh: 0.50),
        EvStationRow(name: 'B'),
        EvStationRow(name: 'C', costPerKwh: 0.30),
      ];
      sortEvRows(rows, EvSortMetric.price);
      expect(rows.first.name, 'C');
      expect(rows.last.name, 'B');
    });
  });

  group('evStationRowFromApi', () {
    test('picks preferred connector when present', () {
      final row = evStationRowFromApi(
        {
          'name': 'Sydney Hub',
          'network': 'Chargefox',
          'distance_km': 2.5,
          'connectors': [
            {'connector_type': 'CCS2', 'max_power_kw': 150, 'cost_per_kwh': 0.42},
            {'connector_type': 'CHAdeMO', 'max_power_kw': 50, 'cost_per_kwh': 0.55},
          ],
        },
        selectedConnectorType: 'CHAdeMO',
      );
      expect(row.name, 'Sydney Hub');
      expect(row.network, 'Chargefox');
      expect(row.connectorType, 'CHAdeMO');
      expect(row.costPerKwh, 0.55);
      expect(row.maxPowerKw, 50);
      expect(row.connectors, hasLength(2));
    });

    test('falls back to first connector when preferred missing', () {
      final row = evStationRowFromApi({
        'name': 'Fallback Hub',
        'connectors': [
          {'connector_type': 'CCS2', 'max_power_kw': 50, 'cost_per_kwh': 0.45},
        ],
      }, selectedConnectorType: 'Tesla');
      expect(row.connectorType, 'CCS2');
      expect(row.costPerKwh, 0.45);
    });

    test('handles empty connectors gracefully', () {
      final row = evStationRowFromApi({
        'name': 'Empty',
        'connectors': <Map<String, dynamic>>[],
      });
      expect(row.costPerKwh, isNull);
      expect(row.maxPowerKw, isNull);
      expect(row.connectors, isEmpty);
    });
  });
}