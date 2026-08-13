// Regression test for AUT-511: the Community Garage screen showed its title
// twice because the Feed tab nested its own Scaffold/AppBar ("Community
// Garage") inside the parent tabbed AppBar (also "Community Garage").

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/community_garage/community_garage_screen.dart';
import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);

  @override
  Future<dynamic> get(String path) async => {'items': []};
}

class _FakeAuthState extends AuthState {
  @override
  ApiClient get api => _FakeApi();
}

void main() {
  testWidgets('Community Garage title appears exactly once', (tester) async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform({});
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>(
        create: (_) => _FakeAuthState(),
        child: const MaterialApp(home: CommunityGarageScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Community Garage'), findsOneWidget);
    expect(find.byType(AppBar), findsOneWidget);
  });
}
