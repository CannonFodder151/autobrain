/// Builds a drawable route from a trip's GPS samples (AUT-395).
///
/// Deterministic — raw coordinates to a polyline, no AI. Invalid `0,0` fixes
/// (no GPS lock) and non-finite/out-of-range points are dropped so a track with
/// gaps still renders. Mirrors the backend `trip_gps.clean_samples` contract.
library;

import 'package:latlong2/latlong.dart';

import 'models.dart';

/// Whether [samples] can draw a meaningful route (2+ valid fixes).
bool hasRoute(List<GpsPoint> samples) => validRoute(samples).length >= 2;

/// Filters invalid `0,0` (no-fix) and out-of-range fixes into a polyline,
/// dropping consecutive duplicates (GPS jitter adds no route information).
List<LatLng> validRoute(List<GpsPoint> samples) {
  final pts = <LatLng>[];
  for (final s in samples) {
    if ((s.lat == 0 && s.lng == 0) ||
        s.lat < -90 ||
        s.lat > 90 ||
        s.lng < -180 ||
        s.lng > 180) {
      continue;
    }
    final p = LatLng(s.lat, s.lng);
    if (pts.isEmpty || p != pts.last) pts.add(p);
  }
  return pts;
}
