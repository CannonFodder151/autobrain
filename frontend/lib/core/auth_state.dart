/// Global auth + navigation state (ChangeNotifier via provider).
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';

class AuthState extends ChangeNotifier {
  AuthState() {
    _restore();
  }

  String? _token;
  String? get token => _token;
  bool get isLoggedIn => _token != null;

  ApiClient? _client;
  ApiClient get api => _client!;

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('auth_token');
    if (_token != null) {
      _client = ApiClient(_token);
      notifyListeners();
    }
  }

  Future<void> login(String email, String password) async {
    final data = await _anonymous().post(
      '/auth/login',
      {'email': email, 'password': password},
    );
    await _persist(data);
  }

  Future<void> register(String email, String name, String password) async {
    final data = await _anonymous().post(
      '/auth/register',
      {'email': email, 'display_name': name, 'password': password},
    );
    await _persist(data);
  }

  Future<void> logout() async {
    _token = null;
    _client = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
    notifyListeners();
  }

  ApiClient _anonymous() => ApiClient(null);

  Future<void> _persist(dynamic data) async {
    final map = data as Map<String, dynamic>;
    _token = map['access_token'] as String;
    _client = ApiClient(_token);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('auth_token', _token!);
    notifyListeners();
  }
}
