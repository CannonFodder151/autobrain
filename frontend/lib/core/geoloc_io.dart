import 'package:geolocator/geolocator.dart';

/// Native GPS via the geolocator plugin (AUT-539).
/// Returns {latitude, longitude} or null when location services are off,
/// permission is denied, or no fix arrives within 10s.
Future<Map<String, double>?> getCurrentPosition() async {
  try {
    if (!await Geolocator.isLocationServiceEnabled()) return null;
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return null;
    }
    final pos = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 10),
      ),
    );
    return {'latitude': pos.latitude, 'longitude': pos.longitude};
  } catch (_) {
    return null;
  }
}
