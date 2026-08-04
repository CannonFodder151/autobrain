import 'dart:async';
import 'dart:html' as html;

/// Best-effort current position via the browser Geolocation API.
/// Returns {latitude, longitude} or null if denied/unavailable.
Future<Map<String, double>?> getCurrentPosition() async {
  try {
    final pos = await html.window.navigator.geolocation.getCurrentPosition(
      enableHighAccuracy: true,
      timeout: const Duration(seconds: 10),
      maximumAge: const Duration(minutes: 1),
    );
    final coords = pos.coords;
    if (coords == null) return null;
    final lat = coords.latitude?.toDouble();
    final lng = coords.longitude?.toDouble();
    if (lat == null || lng == null) return null;
    return {'latitude': lat, 'longitude': lng};
  } catch (_) {
    return null;
  }
}
