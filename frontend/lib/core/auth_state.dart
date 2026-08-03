/// Global auth + navigation state (ChangeNotifier via provider).
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';

enum LoginOutcome { ok, mfaRequired, failed }

class AuthState extends ChangeNotifier {
  AuthState() {
    _restore();
  }

  String? _token;
  String? _role;
  String? _userId;
  String? _mfaToken;
  String? get token => _token;
  String? get role => _role;
  String? get userId => _userId;
  String? get mfaTokenHint => _mfaToken;
  bool get isLoggedIn => _token != null;
  bool get isAdmin => _role == 'admin';

  ApiClient? _client;
  ApiClient get api => _client!;

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('auth_token');
    _role = prefs.getString('auth_role');
    if (_token != null) {
      _client = ApiClient(_token);
      _refreshProfile();
      notifyListeners();
    }
  }

  Future<void> _refreshProfile() async {
    try {
      final data = await _client!.get('/auth/me') as Map<String, dynamic>;
      _role = data['role'] as String?;
      _userId = data['id'] as String?;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('auth_role', _role ?? 'user');
      notifyListeners();
    } catch (_) {}
  }

  Future<LoginOutcome> login(String email, String password) async {
    try {
      final data = await _anonymous().post(
        '/auth/login',
        {'email': email, 'password': password},
      ) as Map<String, dynamic>;
      if (data['mfa_required'] == true && data['mfa_token'] != null) {
        _mfaToken = data['mfa_token'] as String;
        return LoginOutcome.mfaRequired;
      }
      await _persist(data);
      return LoginOutcome.ok;
    } catch (_) {
      return LoginOutcome.failed;
    }
  }

  /// Verifies the second factor and completes a login in progress.
  Future<bool> verifyMfa(String mfaToken, String code) async {
    try {
      final data = await _anonymous().post(
        '/auth/mfa/verify',
        {'mfa_token': mfaToken, 'code': code},
      ) as Map<String, dynamic>;
      await _persist(data);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> logout() async {
    _token = null;
    _role = null;
    _userId = null;
    _client = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
    await prefs.remove('auth_role');
    notifyListeners();
  }

  ApiClient _anonymous() => ApiClient(null);

  Future<void> _persist(Map<String, dynamic> map) async {
    final tokenPair = map['token_pair'];
    if (tokenPair is Map<String, dynamic>) {
      map = tokenPair;
    }
    _token = map['access_token'] as String?;
    _role = ((map['user'] as Map<String, dynamic>?) ?? {})['role'] as String?;
    _userId = ((map['user'] as Map<String, dynamic>?) ?? {})['id'] as String?;
    _client = ApiClient(_token!);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('auth_token', _token!);
    await prefs.setString('auth_role', _role ?? 'user');
    notifyListeners();
  }
}
