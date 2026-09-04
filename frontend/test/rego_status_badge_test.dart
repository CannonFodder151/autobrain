import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/models.dart';
import 'package:autobrain/widgets/rego_status_badge.dart';

void main() {
  Widget _host({required Widget child, bool premium = true}) =>
      MaterialApp(home: Scaffold(body: child));

  Vehicle _v({String? status, String? expiry}) => Vehicle.fromJson({
        'id': 'v1',
        'nickname': 'Daily',
        if (status != null) 'rego_status': status,
        if (expiry != null) 'rego_expiry_date': expiry,
      });

  testWidgets('renders nothing when rego data missing', (t) async {
    await t.pumpWidget(_host(child: RegoStatusBadge(vehicle: _v(), premium: true)));
    expect(find.byType(RegoStatusBadge), findsOneWidget);
    expect(find.textContaining('Rego'), findsNothing);
  });

  testWidgets('renders green badge + expiry for valid', (t) async {
    final v = _v(status: 'valid', expiry: '2027-03-12');
    await t.pumpWidget(_host(child: RegoStatusBadge(vehicle: v, premium: true)));
    expect(find.text('Rego valid'), findsOneWidget);
    expect(find.text('Expires: 12 Mar 2027'), findsOneWidget);
  });

  testWidgets('renders red badge for expired', (t) async {
    final v = _v(status: 'expired', expiry: '2024-01-01');
    await t.pumpWidget(_host(child: RegoStatusBadge(vehicle: v, premium: true)));
    expect(find.text('Rego expired'), findsOneWidget);
  });

  testWidgets('treats Registered/current/active as valid', (t) async {
    for (final s in ['Registered', 'CURRENT', 'Active']) {
      final v = _v(status: s, expiry: '2027-03-12');
      await t.pumpWidget(_host(child: RegoStatusBadge(vehicle: v, premium: true)));
      expect(find.text('Rego valid'), findsOneWidget, reason: 'status=$s');
    }
  });

  testWidgets('hides for free accounts', (t) async {
    final v = _v(status: 'valid', expiry: '2027-03-12');
    await t.pumpWidget(_host(child: RegoStatusBadge(vehicle: v, premium: false)));
    expect(find.text('Rego valid'), findsNothing);
    expect(find.text('Expires:'), findsNothing);
  });

  test('Vehicle.hasRegoData is null-safe', () {
    expect(_v().hasRegoData, isFalse);
    expect(_v(status: 'valid').hasRegoData, isFalse);
    expect(_v(expiry: '2027-03-12').hasRegoData, isFalse);
    expect(_v(status: '', expiry: '2027-03-12').hasRegoData, isFalse);
    expect(_v(status: 'valid', expiry: '').hasRegoData, isFalse);
    expect(_v(status: 'valid', expiry: '2027-03-12').hasRegoData, isTrue);
  });

  test('formattedRegoExpiry formats ISO date', () {
    final v = _v(status: 'valid', expiry: '2027-03-12');
    expect(v.formattedRegoExpiry, '12 Mar 2027');
  });
}