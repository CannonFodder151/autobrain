// AUT-1884: the "Scan fuel receipt" button must open the device CAMERA (not just
// the file library), with a "Choose from files" fallback. This test verifies
// the chooser surface is presented; the ImagePicker camera path itself is
// exercised on device (no flutter toolchain available in CI unit runs).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/fuel/add_fuel_screen.dart';

void main() {
  testWidgets('receipt scan offers camera + files chooser (AUT-1884)',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AuthState(),
        child: const MaterialApp(home: AddFuelScreen(vehicleId: 'veh-1')),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Scan fuel receipt'), findsOneWidget);

    await tester.tap(find.text('Scan fuel receipt'));
    await tester.pumpAndSettle();

    expect(find.text('Take a photo'), findsOneWidget);
    expect(find.text('Choose from files'), findsOneWidget);
  });
}
