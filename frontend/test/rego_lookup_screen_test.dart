import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/screens/rego/rego_lookup_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi(this._handler) : super('test-token');

  final Future<Map<String, dynamic>> Function(String path, Map<String, dynamic> body) _handler;
  String? lastPath;
  Map<String, dynamic>? lastBody;

  @override
  Future<dynamic> post(String path, [Object? body, Map<String, String>? headers]) async {
    lastPath = path;
    lastBody = (body is Map) ? body.cast<String, dynamic>() : <String, dynamic>{};
    if (path.endsWith('/rego-lookup')) {
      return await _handler(path, lastBody!);
    }
    return null;
  }
}

class _FakeAuthState extends AuthState {
  _FakeAuthState({required this.premiumOverride, required this.apiOverride});
  final bool premiumOverride;
  final ApiClient apiOverride;

  @override
  bool get premium => premiumOverride;

  @override
  ApiClient get api => apiOverride;
}

Widget _host({required ApiClient api, required bool premium, Widget? child}) {
  return ChangeNotifierProvider<AuthState>(
    create: (_) => _FakeAuthState(
      premiumOverride: premium,
      apiOverride: api,
    ),
    child: MaterialApp(home: child ?? const RegoLookupScreen()),
  );
}

void main() {
  testWidgets('renders PremiumGate for free accounts', (t) async {
    final api = _FakeApi((_, __) async => <String, dynamic>{});
    await t.pumpWidget(_host(api: api, premium: false));
    expect(find.text('Premium feature'), findsOneWidget);
    expect(find.text('Upgrade to premium'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('renders input card for premium users', (t) async {
    final api = _FakeApi((_, __) async => <String, dynamic>{});
    await t.pumpWidget(_host(api: api, premium: true));
    expect(find.text('Look up'), findsOneWidget);
    expect(find.text('Registration plate'), findsOneWidget);
  });

  testWidgets('shows error when plate is empty', (t) async {
    final api = _FakeApi((_, __) async => <String, dynamic>{});
    await t.pumpWidget(_host(api: api, premium: true));
    await t.tap(find.text('Look up'));
    await t.pumpAndSettle();
    expect(find.textContaining('Enter a registration plate'), findsOneWidget);
  });

  testWidgets('calls /vehicles/rego-lookup with plate + state', (t) async {
    final api = _FakeApi((_, __) async => {
      'rego': 'TCRWN',
      'vin': '6ABC1234567890DEF',
      'make': 'Toyota',
      'model': 'Crown',
      'year': 1997,
      'state': 'VIC',
      'status': 'registered',
      'expiry_date': '2027-03-12',
      'source': 'state-heuristic',
    });
    await t.pumpWidget(_host(api: api, premium: true));
    await t.enterText(find.byType(TextField).first, 'TCRWN');
    await t.tap(find.text('Look up'));
    await t.pumpAndSettle();
    expect(api.lastPath, '/vehicles/rego-lookup');
    expect(api.lastBody?['rego'], 'TCRWN');
    expect(api.lastBody?['state'], 'VIC');
    expect(api.lastBody?['vehicle_type'], 'car');
  });

  testWidgets('renders result card with VIN + status + expiry', (t) async {
    final api = _FakeApi((_, __) async => {
      'rego': 'TCRWN',
      'vin': '6ABC1234567890DEF',
      'make': 'Toyota',
      'model': 'Crown',
      'year': 1997,
      'state': 'VIC',
      'status': 'registered',
      'expiry_date': '2027-03-12',
      'source': 'state-heuristic',
    });
    await t.pumpWidget(_host(api: api, premium: true));
    await t.enterText(find.byType(TextField).first, 'TCRWN');
    await t.tap(find.text('Look up'));
    await t.pumpAndSettle();
    expect(find.text('Rego valid'), findsOneWidget);
    expect(find.text('Expires: 2027-03-12'), findsOneWidget);
    expect(find.text('6ABC1234567890DEF'), findsOneWidget);
    expect(find.textContaining('Toyota Crown'), findsOneWidget);
  });

  testWidgets('renders expired status when provider returns expired', (t) async {
    final api = _FakeApi((_, __) async => {
      'rego': 'X1',
      'make': 'Toyota',
      'model': 'Camry',
      'year': 2019,
      'state': 'NSW',
      'status': 'expired',
      'expiry_date': '2024-01-01',
      'source': 'provider',
    });
    await t.pumpWidget(_host(api: api, premium: true));
    await t.enterText(find.byType(TextField).first, 'X1');
    await t.tap(find.text('Look up'));
    await t.pumpAndSettle();
    expect(find.text('Rego not current'), findsOneWidget);
  });

  testWidgets('shows friendly 403 message', (t) async {
    final api = _FakeApi((_, __) async {
      throw ApiException(403, 'premium feature');
    });
    await t.pumpWidget(_host(api: api, premium: true));
    await t.enterText(find.byType(TextField).first, 'X1');
    await t.tap(find.text('Look up'));
    await t.pumpAndSettle();
    expect(find.textContaining('premium feature'), findsOneWidget);
  });
}
