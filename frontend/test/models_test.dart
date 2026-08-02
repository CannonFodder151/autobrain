import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/models.dart';

void main() {
  test('Vehicle.fromJson parses backend payload', () {
    final v = Vehicle.fromJson(const {
      'id': 'v1',
      'nickname': 'The Whip',
      'rego': 'ABC123',
      'make': 'Toyota',
      'model': 'Camry',
      'year': 2021,
      'odometer_km': 42000,
      'condition': 'good',
      'is_primary': true,
    });
    expect(v.displayName, contains('Toyota'));
    expect(v.year, 2021);
    expect(v.isPrimary, isTrue);
  });

  test('Part.needsReorder', () {
    final low = Part.fromJson(const {
      'id': 'p1',
      'name': 'Oil filter',
      'category': 'filters',
      'quantity': 1,
      'min_quantity': 3,
    });
    expect(low.needsReorder, isTrue);
  });
}
