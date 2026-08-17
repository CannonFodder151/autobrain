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

/// Appends the one-shot provisioning token (AUT-969 F2) to a built payload.
/// The firmware substring-parses each key independently, so the token is
/// appended before the closing brace and order stays irrelevant. The token is
/// hex (never needs escaping). Returns the payload unchanged when [token] is
/// empty so firmware that predates the token (or older boards that don't
/// expose the token characteristic) keep working.
String appendProvisionToken(String payload, String? token) {
  if (token == null || token.isEmpty) return payload;
  final trimmed = payload.trim();
  if (!trimmed.endsWith('}')) return payload;
  return '${trimmed.substring(0, trimmed.length - 1)}'
      ',"prov_token":"$token"}';
}

/// Validates WiFi inputs against the IEEE 802.11 / WPA2 limits before the
/// payload is written over BLE: SSID is 1–32 octets, the WPA2 passphrase is
/// 8–63 octets (AUT-963 F3). Also rejects `"` and `\` in the SSID/pass: the
/// firmware's substring extractor terminates values at the first `"` and never
/// unescapes, so those characters would be silently truncated on the dongle
/// (AUT-968 F2). Returns a user-facing message, or null when provisionable.
/// Maps a firmware ack ("err:…") to a friendly, actionable message.
/// Fw1's first-write-only gate is the one users actually hit on a re-push
/// (AUT-968 F5); other err: are surfaced with the terse prefix stripped.
String provisionAckMessage(String ack) {
  final msg = ack.startsWith('err:') ? ack.substring(4) : ack;
  switch (msg) {
    case 'already configured':
      return 'This dongle is already provisioned — factory-reset it before '
          'pushing new WiFi settings.';
    case 'token missing or expired':
      // AUT-969 F6: the token read raced pairing, or the 120 s provisioning
      // window lapsed mid-flow. The write is fail-closed by design; re-pair
      // and retry quickly.
      return 'The dongle rejected the push. Re-pair and try again immediately '
          'after the phone asks to pair.';
    default:
      return msg.trim();
  }
}

String? validateWifiInput({required String ssid, required String pass}) {
  if (ssid.contains('"') ||
      ssid.contains('\\') ||
      pass.contains('"') ||
      pass.contains('\\')) {
    return 'WiFi name and password cannot contain " or \\ characters.';
  }
  final s = utf8.encode(ssid).length;
  if (s == 0) return 'Enter the WiFi network name (SSID) first.';
  if (s > 32) return 'SSID must be 32 characters or fewer.';
  final p = utf8.encode(pass).length;
  if (p < 8) return 'WiFi password must be at least 8 characters.';
  if (p > 63) return 'WiFi password must be 63 characters or fewer.';
  return null;
}
