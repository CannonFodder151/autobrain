// Regression test for AUT-3104: AuthState.test() must throw in release mode
// and produce a randomised token per instance (never a constant).
//
// Note: kDebugMode is a const evaluated at compile time, so we can't
// simulate release mode in a debug test. The guard is enforced at compile
// time: in release builds the `if (kDebugMode) return` branch is
// tree-shaken, and `_requireDebugMode()` always throws.

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/auth_state.dart';
import 'package:autobrain/core/api_client.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
}

void main() {
  testWidgets('AuthState.test() works in debug mode',
      (WidgetTester tester) async {
    final state = AuthState.test(api: _FakeApi());
    expect(state.isLoggedIn, isTrue);
    expect(state.token, isNotNull);
    expect(state.role, 'user');
    expect(state.freeAccount, isFalse);
  });

  test('AuthState.test() token is randomised per instance', () {
    final a = AuthState.test(api: _FakeApi());
    final b = AuthState.test(api: _FakeApi());
    expect(a.token, isNotNull);
    expect(b.token, isNotNull);
    expect(a.token, isNot(equals(b.token)));
  });
}
