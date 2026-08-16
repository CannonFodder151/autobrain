/// Dongle WiFi provisioning — deterministic payload builder (AUT-936).
///
/// The esp32-diy firmware has NO JSON parser: it extracts `"key":"value"`
/// substrings from the payload. So the provisioning JSON must be COMPACT (no
/// whitespace) and keys must stay in the exact order ssid, pass, api_url,
/// device_id, api_key — the same order the firmware expects. Never
/// pretty-print or reorder this. See docs/api-spec.md (Dongle devices).
library;

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
