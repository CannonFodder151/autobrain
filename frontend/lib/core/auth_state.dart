/// Global auth + navigation state (ChangeNotifier via provider).
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'config.dart';

enum LoginOutcome { ok, mfaRequired, mfaSetupRequired, failed }

class AuthState extends ChangeNotifier {
  AuthState() {
    _restore();
  }

  String? _token;
  String? _role;
  String? _userId;
  String? _mfaToken;
  bool _darkMode = true;
  String? get token => _token;
  String? get role => _role;
  String? get userId => _userId;
  String? get mfaTokenHint => _mfaToken;
  bool get darkMode => _darkMode;
  bool get isLoggedIn => _token != null;
  bool get isAdmin => _role == 'admin';
  bool get isDemo => _role == 'demo';

  Future<void> toggleThemeMode() async {
    _darkMode = !_darkMode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('dark_mode', _darkMode);
    notifyListeners();
  }

  ApiClient? _client;
  ApiClient get api => _client!;

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    await AppConfig.load();
    _token = prefs.getString('auth_token');
    _role = prefs.getString('auth_role');
    _darkMode = prefs.getBool('dark_mode') ?? true;
    if (_token != null) {
      _client = ApiClient(_token);
      _refreshProfile();
      notifyListeners();
    }
  }

  /// Called after the user picks a server — resets any session and rebuilds
  /// the client against the new base URL.
  Future<void> serverChanged() async {
    _token = null;
    _role = null;
    _userId = null;
    _client = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
    await prefs.remove('auth_role');
    notifyListeners();
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
      if (data['mfa_setup_required'] == true && data['mfa_token'] != null) {
        _mfaToken = data['mfa_token'] as String;
        return LoginOutcome.mfaSetupRequired;
      }
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

  /// Starts MFA enrolment during a login in progress (enforced-MFA flow).
  Future<Map<String, dynamic>?> startMfaSetup(String mfaToken) async {
    try {
      return await _anonymous().post(
        '/auth/mfa/setup-session',
        {'mfa_token': mfaToken},
      ) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  /// Completes MFA enrolment, returning true once the session is established.
  Future<bool> completeMfaSetup(String mfaToken, String code) async {
    try {
      final data = await _anonymous().post(
        '/auth/mfa/complete-setup',
        {'mfa_token': mfaToken, 'code': code},
      ) as Map<String, dynamic>;
      await _persist(data);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Requests a password-reset email (always succeeds; server hides existence).
  Future<void> requestPasswordReset(String email) async {
    await _anonymous().post(
      '/auth/password-reset/request',
      {'email': email},
    );
  }

  /// Registers a Free-tier account (hosted instance). Only display name + email
  /// are collected; the server emails a setup link to choose a password and
  /// enable MFA. No auto-login. Returns null on success, or an error message.
  Future<String?> signup({
    required String email,
    required String displayName,
  }) async {
    try {
      await _anonymous().post(
        '/auth/signup',
        {'email': email, 'display_name': displayName},
      );
      return null;
    } on ApiException catch (e) {
      return e.message;
    } catch (_) {
      return 'Could not create your account. Please try again.';
    }
  }

  /// Confirms a password reset with the emailed token.
  Future<bool> confirmPasswordReset(String token, String newPassword) async {
    try {
      await _anonymous().post(
        '/auth/password-reset/confirm',
        {'token': token, 'new_password': newPassword},
      );
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
