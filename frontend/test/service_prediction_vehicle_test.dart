// Regression test for AUT-398: AI service prediction showed the first vehicle
// in the account list (e.g. the Fazer) instead of the vehicle the user had
// selected, because the screen fetched GET /vehicles and used `.first`.
// It must fetch GET /vehicles/{id} and show that vehicle.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/services/service_prediction_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  final List<String> requested = [];

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    requested.add(path);
    if (path == '/vehicles/abc') {
      return {
        'id': 'abc',
        'nickname': 'Crown CBR',
        'make': 'Honda',
        'model': 'CBR500R',
        'year': 2021,
        'odometer_km': 12000,
        'is_primary': false,
      };
    }
    // Old (buggy) fetch used GET /vehicles and took `.first`:
    return [
      {
        'id': 'xyz',
        'nickname': 'Fazer',
        'make': 'Yamaha',
        'model': 'FZ6',
        'year': 2010,
        'odometer_km': 80000,
        'is_primary': true,
      },
    ];
  }
}

class _FakeAuthState extends AuthState {
  _FakeAuthState(this.fakeApi);
  final _FakeApi fakeApi;

  @override
  ApiClient get api => fakeApi;
}

void main() {
  testWidgets(
      'prediction screen fetches and shows the selected vehicle, not the first',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    final fake = _FakeApi();
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthState>(
        create: (_) => _FakeAuthState(fake),
        child: const MaterialApp(
          home: ServicePredictionScreen(vehicleId: 'abc'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(fake.requested, contains('/vehicles/abc'));
    expect(fake.requested, isNot(contains('/vehicles')));
    expect(find.textContaining('Crown CBR'), findsOneWidget);
    expect(find.textContaining('Fazer'), findsNothing);
  });
}
