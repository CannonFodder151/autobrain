import 'package:flutter_secure_storage/test/test_flutter_secure_storage_platform.dart';
import 'package:flutter_secure_storage_platform_interface/flutter_secure_storage_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:autobrain/core/token_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Map<String, String> secure;
  late TokenStore store;

  setUp(() {
    secure = {};
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStoragePlatform.instance = TestFlutterSecureStoragePlatform(secure);
    store = TokenStore();
  });

  test('write then read round-trips token and role', () async {
    await store.write(token: 'jwt-abc', role: 'admin');
    final (token, refresh, role, needsReauth) = await store.readWithMigration();
    expect(token, 'jwt-abc');
    expect(refresh, isNull);
    expect(role, 'admin');
    expect(needsReauth, false);
  });

  test('role defaults to user when not supplied', () async {
    await store.write(token: 'jwt-abc');
    final (_, _, role, _) = await store.readWithMigration();
    expect(role, 'user');
  });

  test('clear removes the stored session', () async {
    await store.write(token: 'jwt-abc', role: 'admin');
    await store.clear();
    final (token, refresh, role, _) = await store.readWithMigration();
    expect(token, isNull);
    expect(refresh, isNull);
    expect(role, isNull);
  });

  test('migrates legacy SharedPreferences session into secure storage', () async {
    SharedPreferences.setMockInitialValues({
      'auth_token': 'legacy-jwt',
      'auth_role': 'demo',
      'dark_mode': true,
    });

    final (token, refresh, role, needsReauth) = await store.readWithMigration();
    expect(token, 'legacy-jwt');
    expect(refresh, isNull);
    expect(role, 'demo');
    expect(needsReauth, true);

    expect(secure['auth_token'], 'legacy-jwt');
    expect(secure['auth_role'], 'demo');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('auth_token'), isFalse);
    expect(prefs.containsKey('auth_role'), isFalse);
    expect(prefs.getBool('dark_mode'), isTrue);
    expect(prefs.getBool('autobrain_legacy_jwt_needs_reauth'), isTrue);
  });

  test('needsReauth returns true only after a legacy migration', () async {
    final prefs = await SharedPreferences.getInstance();
    expect(await store.needsReauth(), isFalse);

    SharedPreferences.setMockInitialValues({'auth_token': 'legacy-jwt'});
    final (_, _, _, needsReauth) = await store.readWithMigration();
    expect(needsReauth, true);
    expect(await store.needsReauth(), isTrue);

    await store.ackReauth();
    expect(await store.needsReauth(), isFalse);
  });

  test('clear wipes the migration flag too', () async {
    SharedPreferences.setMockInitialValues({'auth_token': 'legacy-jwt'});
    await store.readWithMigration();
    await store.clear();
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('autobrain_legacy_jwt_needs_reauth'), isFalse);
  });
}