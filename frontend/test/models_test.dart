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

  test('Vehicle equality is id-based', () {
    final a = Vehicle.fromJson(const {'id': 'v1', 'nickname': 'A'});
    final b = Vehicle.fromJson(const {'id': 'v1', 'nickname': 'B'});
    final c = Vehicle.fromJson(const {'id': 'v2', 'nickname': 'A'});
    expect(a, equals(b));
    expect(a, isNot(equals(c)));
    expect(a.hashCode, b.hashCode);
  });

  test('Vehicle.resolveSelection re-syncs selection to a fresh instance', () {
    final fresh = Vehicle.fromJson(const {'id': 'v1', 'nickname': 'Edited'});
    final other = Vehicle.fromJson(const {'id': 'v2', 'nickname': 'Other'});
    final stale = Vehicle.fromJson(const {'id': 'v1', 'nickname': 'Old'});
    expect(Vehicle.resolveSelection([fresh, other], stale), same(fresh));
  });

  test('Vehicle.resolveSelection falls back when current is gone', () {
    final primary = Vehicle.fromJson(
        const {'id': 'p', 'nickname': 'Primary', 'is_primary': true});
    final other = Vehicle.fromJson(const {'id': 'o', 'nickname': 'Other'});
    final gone = Vehicle.fromJson(const {'id': 'x', 'nickname': 'Gone'});
    expect(Vehicle.resolveSelection([primary, other], gone), same(primary));
    expect(Vehicle.resolveSelection([primary, other], null), same(primary));
    expect(Vehicle.resolveSelection([], gone), isNull);
  });

  test('Vehicle.byId resolves the requested vehicle, not the first', () {
    final crown = Vehicle.fromJson(
        const {'id': 'crown', 'nickname': 'Crown', 'is_primary': true});
    final fazer = Vehicle.fromJson(const {'id': 'fazer', 'nickname': 'Fazer'});
    expect(Vehicle.byId([crown, fazer], 'crown'), same(crown));
    expect(Vehicle.byId([crown, fazer], 'fazer'), same(fazer));
    expect(Vehicle.byId([crown, fazer], 'missing'), same(crown));
    expect(Vehicle.byId([], 'missing'), isNull);
  });

  test('Vehicle.fromJson parses fuel_type (AUT-1819)', () {
    final v = Vehicle.fromJson(const {
      'id': 'f1',
      'nickname': 'The Whip',
      'fuel_type': '98',
    });
    expect(v.fuelType, '98');
  });

  test('Vehicle.fromJson tolerates missing fuel_type (AUT-1819)', () {
    final v = Vehicle.fromJson(const {'id': 'f2', 'nickname': 'No Fuel'});
    expect(v.fuelType, isNull);
  });

  test('Vehicle.fromJson parses share fields', () {
    final v = Vehicle.fromJson(const {
      'id': 's1',
      'nickname': 'The Whip',
      'is_shared': true,
      'shared_by': 'Alice Owner',
    });
    expect(v.isShared, isTrue);
    expect(v.sharedBy, 'Alice Owner');
    expect(v.dropdownLabel, 'The Whip (Invited by Alice Owner)');
  });

  test('Vehicle dropdownLabel unchanged when owned', () {
    final v = Vehicle.fromJson(const {'id': 'o1', 'nickname': 'Mine'});
    expect(v.isShared, isFalse);
    expect(v.dropdownLabel, 'Mine');
  });

  group('LogEntry auto source labels', () {
    test('car_auto trips are auto-logged as "auto (car kit)"', () {
      final e = LogEntry.fromJson(const {
        'id': 'l1',
        'source': 'car_auto',
        'status': 'completed',
        'started_at': '2026-08-01T09:00:00Z',
      });
      expect(e.isAutoLogged, isTrue);
      expect(e.autoSourceLabel, 'auto (car kit)');
    });

    test('obd_auto trips keep the OBD label', () {
      final e = LogEntry.fromJson(const {
        'id': 'l2',
        'source': 'obd_auto',
        'status': 'completed',
      });
      expect(e.isAutoLogged, isTrue);
      expect(e.autoSourceLabel, 'auto (OBD)');
    });

    test('manual trips are not auto-logged', () {
      final e = LogEntry.fromJson(const {'id': 'l3', 'source': 'manual'});
      expect(e.isAutoLogged, isFalse);
    });
  });

  group('Vehicle powertrain', () {
    test('defaults to ICE when absent', () {
      final v = Vehicle.fromJson(const {'id': 'v1', 'nickname': 'Old'});
      expect(v.powertrain, 'ICE');
    });

    test('parses EV', () {
      final v = Vehicle.fromJson(const {'id': 'v2', 'nickname': 'Tesla', 'powertrain': 'EV'});
      expect(v.powertrain, 'EV');
      expect(PowertrainType.isElectric('EV'), isTrue);
    });

    test('isElectric covers EV/HEV/PHEV, not ICE', () {
      expect(PowertrainType.isElectric('ICE'), isFalse);
      expect(PowertrainType.isElectric('EV'), isTrue);
      expect(PowertrainType.isElectric('HEV'), isTrue);
      expect(PowertrainType.isElectric('PHEV'), isTrue);
      expect(PowertrainType.isElectric(null), isFalse);
    });
  });
}
