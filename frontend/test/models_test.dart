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
}
