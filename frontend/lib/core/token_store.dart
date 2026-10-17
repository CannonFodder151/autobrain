import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _tokenKey = 'auth_token';
const _refreshKey = 'auth_refresh_token';
const _roleKey = 'auth_role';
const _needsReauthKey = 'autobrain_legacy_jwt_needs_reauth';

const _aOptions = AndroidOptions(encryptedSharedPreferences: true);
const _iOptions = IOSOptions(accessibility: KeychainAccessibility.first_unlock);
const _lOptions = LinuxOptions();
const _wOptions = WebOptions();
const _mOptions = MacOsOptions();

class TokenStore {
  TokenStore()
      : _secure = const FlutterSecureStorage(
          aOptions: _aOptions,
          iOptions: _iOptions,
          lOptions: _lOptions,
          wOptions: _wOptions,
          mOptions: _mOptions,
        );

  final FlutterSecureStorage _secure;

  Future<(String?, String?, String?, bool)> readWithMigration() async {
    var token = await _secure.read(key: _tokenKey);
    var refresh = await _secure.read(key: _refreshKey);
    var role = await _secure.read(key: _roleKey);
    var needsReauth = false;

    if (token == null) {
      final prefs = await SharedPreferences.getInstance();
      token = prefs.getString(_tokenKey);
      refresh = prefs.getString(_refreshKey);
      role = prefs.getString(_roleKey);
      if (token != null) {
        needsReauth = true;
        await prefs.remove(_tokenKey);
        await prefs.remove(_refreshKey);
        await prefs.remove(_roleKey);
        await prefs.setBool(_needsReauthKey, true);
      }
    }

    return (token, refresh, role, needsReauth);
  }

  Future<(String?, String?, String?)> read() async {
    final (token, refresh, role, _) = await readWithMigration();
    return (token, refresh, role);
  }

  Future<void> write({
    required String token,
    String? refreshToken,
    String? role,
  }) async {
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
    await _clearMigrationFlag();
  }

  Future<bool> needsReauth() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_needsReauthKey) ?? false;
  }

  Future<void> _clearMigrationFlag() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_needsReauthKey);
  }

  Future<void> ackReauth() => _clearMigrationFlag();
}
