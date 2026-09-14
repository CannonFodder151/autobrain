import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/core/theme.dart';
import 'package:autobrain/core/models.dart';
import 'package:autobrain/screens/home/home_screen.dart';
import 'package:autobrain/screens/vehicles/vehicle_list_screen.dart';
import 'package:autobrain/widgets/responsive.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '/vehicles') {
      return <dynamic>[
        Vehicle(
          id: 'v1',
          nickname: 'Demo Car',
          make: 'Toyota',
          model: 'Camry',
          year: 2022,
          rego: 'ABC123',
          regoState: 'NSW',
          colour: 'White',
          bodyType: 'Sedan',
          fuelType: 'Petrol',
          odometerKm: 45000,
          isPrimary: true,
          isShared: false,
        ),
      ];
    }
    if (path == '/vehicle-shares') return <dynamic>[];
    return <String, dynamic>{};
  }
}

class _FakeAuth extends AuthState {
  _FakeAuth() : super.test(api: _FakeApi());

  @override
  bool get darkMode => true;
}

const _kSizes = {
  '1280': Size(1280, 720),
  '1440': Size(1440, 900),
  '1920': Size(1920, 1080),
};

Future<void> _pumpAtSize(WidgetTester tester, Widget child, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  await tester.pumpWidget(
    ChangeNotifierProvider<AuthState>(
      create: (_) => _FakeAuth(),
      child: MaterialApp(
        theme: AppTheme.dark(),
        home: MediaQuery(
          data: MediaQueryData(size: size),
          child: child,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('HomeScreen desktop layout goldens', () {
    for (final entry in _kSizes.entries) {
      final width = entry.key;
      testWidgets('home $width dark desktop', (WidgetTester tester) async {
        await _pumpAtSize(tester, const HomeScreen(), entry.value);
        await expectLater(
          find.byType(HomeScreen),
          matchesGoldenFile('test/goldens/home_screen/${width}_dark.png'),
        );
      });
    }
  });

  group('VehicleListScreen desktop layout goldens', () {
    for (final entry in _kSizes.entries) {
      final width = entry.key;
      testWidgets('vehicle list $width dark desktop',
          (WidgetTester tester) async {
        await _pumpAtSize(tester, const VehicleListScreen(), entry.value);
        await expectLater(
          find.byType(VehicleListScreen),
          matchesGoldenFile('test/goldens/vehicle_list_screen/${width}_dark.png'),
        );
      });
    }
  });
}
