// Regression test for AUT-893: checkboxes in the share-scope picker used to do
// nothing because the picker mutated the shared scope without triggering a
// rebuild. Toggling any checkbox must flip the value and re-render the box.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/community_garage/widgets/share_scope_picker.dart';

void main() {
  testWidgets('toggling a checkbox updates the scope and re-renders',
      (tester) async {
    final scope = ShareScopeState();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: _Host(scope: scope),
      ),
    ));

    final odometer = find.text('Odometer');
    expect(tester.widget<CheckboxListTile>(
        find.ancestor(of: odometer, matching: find.byType(CheckboxListTile))).value,
        isFalse);

    await tester.tap(odometer);
    await tester.pumpAndSettle();

    expect(scope.allowOdometer, isTrue);
    expect(tester.widget<CheckboxListTile>(
        find.ancestor(of: odometer, matching: find.byType(CheckboxListTile))).value,
        isTrue);

    await tester.tap(odometer);
    await tester.pumpAndSettle();

    expect(scope.allowOdometer, isFalse);
    expect(tester.widget<CheckboxListTile>(
        find.ancestor(of: odometer, matching: find.byType(CheckboxListTile))).value,
        isFalse);
  });
}

class _Host extends StatefulWidget {
  const _Host({required this.scope});

  final ShareScopeState scope;

  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  @override
  Widget build(BuildContext context) {
    return ShareScopePicker(
      scope: widget.scope,
      onChanged: () => setState(() {}),
    );
  }
}
