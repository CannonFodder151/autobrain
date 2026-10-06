import 'dart:async';

import 'package:geolocator/geolocator.dart';

import 'location_result.dart';

/// Native GPS via the geolocator plugin (AUT-539).
/// Returns a [LocationResult] with coordinates or a typed failure reason.
Future<LocationResult> getCurrentPosition() async {
  try {
    if (!await Geolocator.isLocationServiceEnabled()) {
      return const LocationResult.serviceDisabled();
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied) {
      return const LocationResult.permissionDenied();
    }
    if (permission == LocationPermission.deniedForever) {
      return const LocationResult.permissionDeniedForever();
    }
    final pos = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 10),
      ),
    );
    return LocationResult.success(pos.latitude, pos.longitude);
  } on TimeoutException {
    return const LocationResult.timeout();
  } catch (_) {
    return const LocationResult.unexpectedError();
  }
}
