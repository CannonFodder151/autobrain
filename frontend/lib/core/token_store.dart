import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Auth session persistence: the JWT and role live in platform secure storage
/// (Android Keystore / iOS Keychain) so they are not readable as plaintext on
/// disk. Non-sensitive prefs (server picker, dark mode) stay in
/// SharedPreferences.
class TokenStore {
  TokenStore({FlutterSecureStorage? secure})
      : _secure = secure ?? const FlutterSecureStorage();

  final FlutterSecureStorage _secure;

  static const _tokenKey = 'auth_token';
  static const _roleKey = 'auth_role';

  /// Reads the stored session, migrating the legacy SharedPreferences copy
  /// (written before this change) into secure storage on first read.
  Future<(String?, String?)> read() async {
    var token = await _secure.read(key: _tokenKey);
    var role = await _secure.read(key: _roleKey);
    if (token == null) {
      final prefs = await SharedPreferences.getInstance();
      token = prefs.getString(_tokenKey);
      role = prefs.getString(_roleKey);
      if (token != null) {
        await write(token: token, role: role);
        await prefs.remove(_tokenKey);
        await prefs.remove(_roleKey);
      }
    } else if (role == null) {
      role = 'user';
      await _secure.write(key: _roleKey, value: role);
    }
    return (token, role);
  }

  Future<void> write({required String token, String? role}) async {
    await _secure.write(key: _tokenKey, value: token);
    await _secure.write(key: _roleKey, value: role ?? 'user');
  }

  Future<void> clear() async {
    await _secure.delete(key: _tokenKey);
    await _secure.delete(key: _roleKey);
  }
}
