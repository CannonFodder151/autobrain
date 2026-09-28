import 'dart:async';
import 'dart:html' as html;

import 'location_result.dart';

/// Best-effort current position via the browser Geolocation API.
/// Returns a [LocationResult] with coordinates or a typed failure reason.
Future<LocationResult> getCurrentPosition() async {
  try {
    final pos = await html.window.navigator.geolocation.getCurrentPosition(
      enableHighAccuracy: true,
      timeout: const Duration(seconds: 10),
      maximumAge: const Duration(minutes: 1),
    );
    final coords = pos.coords;
    if (coords == null) return const LocationResult.unexpectedError();
    final lat = coords.latitude?.toDouble();
    final lng = coords.longitude?.toDouble();
    if (lat == null || lng == null) return const LocationResult.unexpectedError();
    return LocationResult.success(lat, lng);
  } on TimeoutException {
    return const LocationResult.timeout();
  } catch (_) {
    return const LocationResult.permissionDenied();
  }
}