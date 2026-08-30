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
    expect(await store.read(), ('jwt-abc', null, 'admin'));
  });

  test('role defaults to user when not supplied', () async {
    await store.write(token: 'jwt-abc');
    expect(await store.read(), ('jwt-abc', null, 'user'));
  });

  test('clear removes the stored session', () async {
    await store.write(token: 'jwt-abc', role: 'admin');
    await store.clear();
    expect(await store.read(), (null, null, null));
  });

  test('migrates legacy SharedPreferences session into secure storage', () async {
    SharedPreferences.setMockInitialValues({
      'auth_token': 'legacy-jwt',
      'auth_role': 'demo',
      'dark_mode': true,
    });

    expect(await store.read(), ('legacy-jwt', null, 'demo'));

    expect(secure['auth_token'], 'legacy-jwt');
    expect(secure['auth_role'], 'demo');
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.containsKey('auth_token'), isFalse);
    expect(prefs.containsKey('auth_role'), isFalse);
    expect(prefs.getBool('dark_mode'), isTrue);
  });
}
