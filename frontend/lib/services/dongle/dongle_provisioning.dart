/// Dongle WiFi provisioning — deterministic payload builder (AUT-936).
///
/// The esp32-diy firmware has NO JSON parser: it extracts `"key":"value"`
/// substrings from the payload. So the provisioning JSON must be COMPACT (no
/// whitespace) and keys must stay in the exact order ssid, pass, api_url,
/// device_id, api_key — the same order the firmware expects. Never
/// pretty-print or reorder this. See docs/api-spec.md (Dongle devices).
library;

import 'dart:convert';

/// Builds the one-shot BLE provisioning payload.
///
/// [apiUrl] is optional — the firmware defaults to the hosted API when it is
/// empty, so self-hosted users pass their own base while hosted users omit it.
String buildProvisioningPayload({
  required String ssid,
  required String pass,
  required String deviceId,
  required String apiKey,
  String? apiUrl,
}) {
  final s = _escape(ssid);
  final p = _escape(pass);
  final d = _escape(deviceId);
  final k = _escape(apiKey);
  final u = (apiUrl == null || apiUrl.isEmpty)
      ? ''
      : ',"api_url":"${_escape(apiUrl)}"';
  return '{"ssid":"$s","pass":"$p"$u,"device_id":"$d","api_key":"$k"}';
}

String _escape(String value) =>
    value.replaceAll('\\', '\\\\').replaceAll('"', '\\"');

/// Validates WiFi inputs against the IEEE 802.11 / WPA2 limits before the
/// payload is written over BLE: SSID is 1–32 octets, the WPA2 passphrase is
/// 8–63 octets (AUT-963 F3). Returns a user-facing message, or null when the
/// inputs are provisionable.
String? validateWifiInput({required String ssid, required String pass}) {
  final s = utf8.encode(ssid).length;
  if (s == 0) return 'Enter the WiFi network name (SSID) first.';
  if (s > 32) return 'SSID must be 32 characters or fewer.';
  final p = utf8.encode(pass).length;
  if (p < 8) return 'WiFi password must be at least 8 characters.';
  if (p > 63) return 'WiFi password must be 63 characters or fewer.';
  return null;
}
