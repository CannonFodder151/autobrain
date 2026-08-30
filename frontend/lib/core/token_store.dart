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
  static const _refreshKey = 'auth_refresh_token';
  static const _roleKey = 'auth_role';

  /// Reads the stored session, migrating the legacy SharedPreferences copy
  /// (written before this change) into secure storage on first read.
  Future<(String?, String?, String?)> read() async {
    var token = await _secure.read(key: _tokenKey);
    var refresh = await _secure.read(key: _refreshKey);
    var role = await _secure.read(key: _roleKey);
    if (token == null) {
      final prefs = await SharedPreferences.getInstance();
      token = prefs.getString(_tokenKey);
      refresh = prefs.getString(_refreshKey);
      role = prefs.getString(_roleKey);
      if (token != null) {
        await write(token: token, refreshToken: refresh, role: role);
        await prefs.remove(_tokenKey);
        await prefs.remove(_refreshKey);
        await prefs.remove(_roleKey);
      }
    } else if (role == null) {
      role = 'user';
      await _secure.write(key: _roleKey, value: role);
    }
    return (token, refresh, role);
  }

  Future<void> write({required String token, String? refreshToken, String? role}) async {
    await _secure.write(key: _tokenKey, value: token);
    if (refreshToken != null) {
      await _secure.write(key: _refreshKey, value: refreshToken);
    }
    await _secure.write(key: _roleKey, value: role ?? 'user');
  }

  Future<void> clear() async {
    await _secure.delete(key: _tokenKey);
    await _secure.delete(key: _refreshKey);
    await _secure.delete(key: _roleKey);
  }
}
