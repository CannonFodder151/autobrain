// Basic Flutter widget test.
//
// Pumps the full app shell (provider + AutoBrainApp) and verifies it builds
// without throwing. AuthState restores from SharedPreferences, which in tests
// has no stored token, so the login/server-setup screen renders.

import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/app.dart';
import 'package:autobrain/core/auth_state.dart';

void main() {
  testWidgets('App shell builds', (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AuthState(),
        child: const AutoBrainApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(ChangeNotifierProvider<AuthState>), findsOneWidget);
  });
}
