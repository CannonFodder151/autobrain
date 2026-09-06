import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/models.dart';

void main() {
  test('ElectricityLog.fromJson parses backend payload', () {
    final l = ElectricityLog.fromJson(const {
      'id': 'e1',
      'vehicle_id': 'v1',
      'charge_date': '2026-05-10',
      'odometer_km': 1234,
      'kwh': 42.5,
      'price_per_kwh': 0.32,
      'total_cost': 13.6,
      'is_full_charge': true,
      'distance_km': 250.0,
      'km_per_kwh': 5.88,
      'cost_per_km': 0.0544,
      'notes': 'home wallbox',
      'receipt_id': null,
      'created_at': '2026-05-10T12:00:00Z',
    });
    expect(l.id, 'e1');
    expect(l.chargeDate, '2026-05-10');
    expect(l.kwh, 42.5);
    expect(l.pricePerKwh, 0.32);
    expect(l.totalCost, 13.6);
    expect(l.kmPerKwh, 5.88);
    expect(l.costPerKm, 0.0544);
    expect(l.notes, 'home wallbox');
    expect(l.isFullCharge, isTrue);
  });

  test('ElectricityLog.fromJson handles missing efficiency fields', () {
    final l = ElectricityLog.fromJson(const {
      'id': 'e2',
      'vehicle_id': 'v1',
      'charge_date': '2026-05-11',
      'odometer_km': 1300,
      'kwh': 10.0,
      'price_per_kwh': 0.5,
      'total_cost': 5.0,
    });
    expect(l.kmPerKwh, isNull);
    expect(l.costPerKm, isNull);
    expect(l.isFullCharge, isTrue); // default
    expect(l.notes, isNull);
    expect(l.receiptId, isNull);
  });
}
