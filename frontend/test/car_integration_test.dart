// Tests for the mobile-only "Car Play / Android Auto Integration" settings
// submenu (AUT-366): status-line formatting + explainer/toggle rendering.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/settings/car_integration_screen.dart';
import 'package:autobrain/services/car/car_kit_trip_monitor.dart';
import 'package:autobrain/services/obd/obd_connection.dart';

void main() {
  group('carIntegrationStatusLine', () {
    test('off and no trips', () {
      expect(
        carIntegrationStatusLine(
            connectionStatus: ObdStatus.off,
            tripActive: false,
            lastTripAt: null),
        'Not connected',
      );
    });

    test('connected shows adapter label', () {
      expect(
        carIntegrationStatusLine(
            connectionStatus: ObdStatus.connected,
            adapterLabel: 'VGate iCar Pro',
            tripActive: false,
            lastTripAt: null),
        'Connected — VGate iCar Pro',
      );
    });

    test('car-kit linked without an adapter shows the car-kit signal', () {
      expect(
        carIntegrationStatusLine(
          connectionStatus: ObdStatus.off,
          tripActive: false,
          lastTripAt: null,
          carKitLink: CarKitLinkState.connected,
        ),
        'Car-kit connected',
      );
    });

    test('active trip shows recording since', () {
      final line = carIntegrationStatusLine(
        connectionStatus: ObdStatus.connected,
        adapterLabel: 'VGate',
        tripActive: true,
        tripStartedAt: DateTime(2026, 8, 11, 7, 5),
      );
      expect(line, contains('recording since 11/08 07:05'));
    });

    test('last trip shown when not recording', () {
      final line = carIntegrationStatusLine(
        connectionStatus: ObdStatus.off,
        tripActive: false,
        lastTripAt: DateTime(2026, 8, 10, 18, 30),
      );
      expect(line, contains('last auto trip 10/08 18:30'));
    });
  });

  testWidgets('explainer + toggle render', (tester) async {
    SharedPreferences.setMockInitialValues({'car_auto_trip_logging': true});
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AuthState(),
        child: const MaterialApp(home: CarIntegrationScreen()),
      ),
    );
    await tester.pump();
    expect(find.text('Car Play / Android Auto'), findsOneWidget);
    expect(find.text('Auto trip logging'), findsOneWidget);
    expect(find.text('Head-unit OBD gauges'), findsOneWidget);
    expect(find.text('CarPlay OBD'), findsOneWidget);
    expect(
      find.text('Auto-start trip logging when connected to the car'),
      findsOneWidget,
    );
  });
}
