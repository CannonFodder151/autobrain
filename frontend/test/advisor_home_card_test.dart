// Widget tests for the Ownership Advisor launch card on HomeScreen (AUT-2478).
// Only asserts the card renders with the title, tagline, and six module-chips;
// no network / no AdvisorOverviewScreen drill-in (that is covered by
// advisor_overview_test.dart).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/home/home_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '/vehicles') {
      return <dynamic>[
        {
          'id': 'v-1',
          'nickname': 'My Car',
          'make': 'Toyota',
          'model': 'Camry',
          'year': 2020,
          'odometerKm': 45000,
          'rego': 'ABC123',
          'vehicleType': 'car',
          'condition': 'good',
          'bodyType': 'Sedan',
          'colour': 'White',
          'isShared': false,
          'sharedBy': null,
          'hasRegoData': false,
          'clubReg': false,
        }
      ];
    }
    return <String, dynamic>{};
  }
}

class _FakeAuth extends AuthState {
  @override
  ApiClient get api => _FakeApi();
}

void main() {
  testWidgets('Ownership Advisor launch card renders title, tagline and six chips',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>(
        create: (_) => _FakeAuth(),
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ownership Advisor'), findsWidgets);
    expect(find.text('Live now'), findsOneWidget);
    expect(find.text('What should you do with your car?'), findsOneWidget);

    expect(find.text('Value'), findsOneWidget);
    expect(find.text('Replace'), findsOneWidget);
    expect(find.text('Upgrade'), findsOneWidget);
    expect(find.text('Finance'), findsOneWidget);
    expect(find.text('Dream'), findsOneWidget);
    expect(find.text('AI'), findsOneWidget);
  });

  testWidgets('Launch card is tappable and opens AdvisorOverviewScreen',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>(
        create: (_) => _FakeAuth(),
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('What should you do with your car?'));
    await tester.pumpAndSettle();

    expect(find.text('Overview'), findsOneWidget);
    expect(find.text('AI'), findsWidgets);
  });
}
