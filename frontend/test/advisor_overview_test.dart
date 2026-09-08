// Widget tests for the Ownership Advisor front-door.
//
// The single Ownership Advisor home card (autobrain-monorepo spec) and the
// nested Overview -> 6 sub-modules via chips + tab bar are covered here.
// These tests do not hit the network: they only assert the overview shell
// renders the seven tabs and that the initial tab is selected.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/screens/advisor/overview_screen.dart';

void main() {
  late ApiClient fakeApi;

  setUp(() {
    fakeApi = ApiClient('fake-test-token');
  });

  Future<void> _pumpOverview(WidgetTester tester, int tab) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AuthState.test(api: fakeApi),
        child: MaterialApp(
          home: AdvisorOverviewScreen(
            vehicleId: 'v-1',
            initialTabIndex: tab,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('AdvisorOverviewScreen renders seven tab labels',
      (WidgetTester tester) async {
    await _pumpOverview(tester, 0);
    expect(find.text('Ownership Advisor'), findsOneWidget);

    // The TabBar shows all 7 tab labels at once.
    final tabBarFinder = find.byType(TabBar);
    expect(tabBarFinder, findsOneWidget);
    final tabTexts = tester.widgetList<Text>(
      find.descendant(of: tabBarFinder, matching: find.byType(Text)),
    );
    final labels = tabTexts.map((t) => t.data).toList();
    expect(labels, containsAll([
      'Overview', 'Value', 'Replace', 'Upgrade', 'Finance', 'Dream', 'AI',
    ]));
  });

  testWidgets('initialTabIndex 4 selects Finance tab',
      (WidgetTester tester) async {
    await _pumpOverview(tester, 4);
    // Finance input form should render (it does not depend on API data).
    expect(find.text('Down payment (AUD)'), findsOneWidget);
  });

  testWidgets('Module chips render on the Overview tab',
      (WidgetTester tester) async {
    await _pumpOverview(tester, 0);
    expect(find.byType(ActionChip), findsNWidgets(6));
  });
}
