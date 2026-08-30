// Tests for AUT-1818: Servo Spy is premium-gated (free accounts never see the
// Map/List shell; paid accounts get the theme-aware Map/List segmented view).

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/servo_spy/servo_spy_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async => [];
}

class _FakeFreeAuth extends AuthState {
  @override
  bool get freeAccount => true;
  @override
  ApiClient get api => _FakeApi();
}

class _FakePaidAuth extends AuthState {
  @override
  bool get freeAccount => false;
  @override
  ApiClient get api => _FakeApi();
}

Widget _app(AuthState auth) => ChangeNotifierProvider<AuthState>(
      create: (_) => auth,
      child: MaterialApp(home: const ServoSpyScreen()),
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform({});
  });

  testWidgets('free account is shown the premium gate, not the Map/List shell',
      (tester) async {
    await tester.pumpWidget(_app(_FakeFreeAuth()));
    await tester.pumpAndSettle();

    expect(find.text('Upgrade to premium'), findsOneWidget);
    expect(find.byType(SegmentedButton), findsNothing);
  });

  testWidgets('paid account gets the Map/List segmented control', (tester) async {
    await tester.pumpWidget(_app(_FakePaidAuth()));
    await tester.pumpAndSettle();

    expect(find.text('Map'), findsWidgets);
    expect(find.text('List'), findsWidgets);
    expect(find.text('Upgrade to premium'), findsNothing);
  });

  testWidgets('paid account can switch Map -> List and see the filter button',
      (tester) async {
    await tester.pumpWidget(_app(_FakePaidAuth()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('List'));
    await tester.pump();

    expect(find.byTooltip('Filters'), findsOneWidget);
  });
}
