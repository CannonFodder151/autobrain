// Regression test for AUT-428: the "Get the mobile app" menu item and the
// download dialog must not appear inside the mobile app itself. Flutter test
// VMs run with kIsWeb=false (mobile path), so the item must be absent.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/home/home_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  @override
  Future<dynamic> get(String path) async {
    if (path == '/vehicles') return <dynamic>[];
    return <String, dynamic>{};
  }
}

class _FakeAuth extends AuthState {
  @override
  ApiClient get api => _FakeApi();
}

void main() {
  testWidgets('mobile build hides "Get the mobile app" menu item',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>(
        create: (_) => _FakeAuth(),
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byType(PopupMenuButton<String>));
    await tester.pumpAndSettle();

    expect(find.text('Get the mobile app'), findsNothing);
    expect(find.text('Settings & security'), findsOneWidget);
  });
}
