// Regression test for AUT-4327: the login page logo must be contained
// (not stretched) inside a circular container with a black background.
//
// Verifies the logo container has a black background, a circular shape,
// and the image uses(BoxFit.contain so non-square logos are not stretched.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/auth/login_screen.dart';

void main() {
  Widget wrap() => ChangeNotifierProvider<AuthState>(
        create: (_) => AuthState(),
        child: const MaterialApp(home: LoginScreen()),
      );

  testWidgets('login logo is circular, black background, not stretched',
      (WidgetTester tester) async {
    await tester.pumpWidget(wrap());
    await tester.pumpAndSettle();

    // Scope to the logo subtree: find.byType(Container).first matches the
    // Scaffold body Container at login_screen.dart:181, which is a strict
    // ancestor of the logo Container, so it is visited first in pre-order
    // traversal. ClipOval is unique to the logo, so anchoring on it is
    // order-independent.
    final Container container =
        tester.widget(find.ancestor(
      of: find.byType(ClipOval),
      matching: find.byType(Container),
    ).first);
    expect(container.decoration, isA<BoxDecoration>());
    final BoxDecoration box =
        container.decoration as BoxDecoration;
    expect(box.shape, equals(BoxShape.circle));
    expect(box.color, equals(Colors.black));

    final Image image = tester.widget(find.descendant(
      of: find.byType(ClipOval),
      matching: find.byType(Image),
    ));
    expect(image.fit, equals(BoxFit.contain));
  });
}