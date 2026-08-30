// Regression test for AUT-20: the sign-up page's "Already have an account?
// Sign in" link navigated to a blank page when the sign-up page was the app's
// root route (e.g. opened from the website ?signup=1 link) instead of being
// pushed on top of the login screen.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/auth/login_screen.dart';
import 'package:autobrain/screens/auth/signup_screen.dart';

void main() {
  Widget wrap(Widget home) => ChangeNotifierProvider<AuthState>(
        create: (_) => AuthState(),
        child: MaterialApp(home: home),
      );

  testWidgets('sign-in link from root signup opens login, not a blank page',
      (WidgetTester tester) async {
    await tester.pumpWidget(wrap(const SignupScreen()));
    expect(find.byType(SignupScreen), findsOneWidget);

    await tester.tap(find.text('Already have an account? Sign in'));
    await tester.pumpAndSettle();

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(SignupScreen), findsNothing);
  });

  testWidgets('sign-in link from pushed signup pops back to the login screen',
      (WidgetTester tester) async {
    await tester.pumpWidget(wrap(const Scaffold(body: Text('origin'))));

    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.push(MaterialPageRoute(builder: (_) => const SignupScreen()));
    await tester.pumpAndSettle();
    expect(find.byType(SignupScreen), findsOneWidget);

    await tester.tap(find.text('Already have an account? Sign in'));
    await tester.pumpAndSettle();

    expect(find.byType(SignupScreen), findsNothing);
    expect(find.text('origin'), findsOneWidget);
  });
}
