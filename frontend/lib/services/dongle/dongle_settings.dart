/// Dongle WiFi-upload settings persistence (AUT-936).
///
/// Non-sensitive prefs (toggle, ssid, device id) live in SharedPreferences;
/// the WiFi password and the one-time device API key are device credentials,
/// so they go in flutter_secure_storage (Keystore/Keychain) — same rule as
/// auth tokens (see core/auth_state.dart).
library;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DongleSettings {
  static const _enabled = 'dongle_wifi_enabled';
  static const _ssid = 'dongle_wifi_ssid';
  static const _deviceId = 'dongle_device_id';
  static const _deviceName = 'dongle_device_name';
  static const _vehicleId = 'dongle_vehicle_id';
  static const _bleId = 'dongle_ble_id'; // AUT-1573: confirmed BLE remoteId
  static const _pass = 'dongle_wifi_pass';
  static const _apiKey = 'dongle_api_key';
  static const _storage = FlutterSecureStorage();

  /// Remembers which physical dongle the user confirmed (BLE remoteId) so
  /// auto-connect can target it without re-asking (AUT-1573).
  static Future<void> saveBleId(String? bleId) async {
    final prefs = await SharedPreferences.getInstance();
    if (bleId == null || bleId.isEmpty) {
      await prefs.remove(_bleId);
    } else {
      await prefs.setString(_bleId, bleId);
    }
  }

  /// Persists the provisioning inputs so the user can re-push over BLE
  /// without re-entering them.
  static Future<void> save({
    required bool enabled,
    required String ssid,
    required String pass,
    String? deviceId,
    String? deviceName,
    String? vehicleId,
    String? apiKey,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_enabled, enabled);
    await prefs.setString(_ssid, ssid);
    if (deviceId != null) await prefs.setString(_deviceId, deviceId);
    if (deviceName != null) await prefs.setString(_deviceName, deviceName);
    if (vehicleId != null) await prefs.setString(_vehicleId, vehicleId);
    await _storage.write(key: _pass, value: pass);
    if (apiKey != null) await _storage.write(key: _apiKey, value: apiKey);
  }

  static Future<DongleConfig> load() async {
    final prefs = await SharedPreferences.getInstance();
    final pass = await _storage.read(key: _pass) ?? '';
    final apiKey = await _storage.read(key: _apiKey);
    return DongleConfig(
      enabled: prefs.getBool(_enabled) ?? false,
      ssid: prefs.getString(_ssid) ?? '',
      pass: pass,
      deviceId: prefs.getString(_deviceId),
      deviceName: prefs.getString(_deviceName),
      vehicleId: prefs.getString(_vehicleId),
      apiKey: apiKey,
    );
  }

  /// The BLE remoteId of the user-confirmed dongle, or null.
  static Future<String?> loadBleId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_bleId);
  }

  /// Clears every dongle store — the credentials in secure storage
  /// (WiFi password + one-time API key) and the non-sensitive prefs.
  /// Called on logout / server switch so a previous account's device key
  /// can never be pushed from another account (AUT-963 F1).
  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    for (final key in prefs.getKeys().where((k) => k.startsWith('dongle_'))) {
      await prefs.remove(key);
    }
    await _storage.delete(key: _pass);
    await _storage.delete(key: _apiKey);
  }
}

class DongleConfig {
  final bool enabled;
  final String ssid;
  final String pass;
  final String? deviceId;
  final String? deviceName;
  final String? vehicleId;
  final String? apiKey;

  const DongleConfig({
    required this.enabled,
    required this.ssid,
    required this.pass,
    this.deviceId,
    this.deviceName,
    this.vehicleId,
    this.apiKey,
  });

  /// True when enough is saved to re-push provisioning without re-entering.
  bool get provisionable =>
      ssid.isNotEmpty && deviceId != null && apiKey != null;
}
