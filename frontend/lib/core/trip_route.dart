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

/// Max polyline points encoded into the Google Maps URL. The `path` URL
/// parameter draws the raw track; Android intent/URL length limits make a few
/// hundred points the safe ceiling for a several-thousand-point route.
const int googleMapsMaxPathPoints = 400;

/// Builds a `www.google.com/maps` URL that opens Google Maps with the trip
/// route drawn on it (AUT-427). Pure + deterministic so it unit-tests. Falls
/// back to a plain `q=` coordinate URL when the route is too short to draw.
String googleMapsRouteUrl(List<LatLng> route) {
  if (route.isEmpty) return 'https://www.google.com/maps';
  final pts = _downsample(route, googleMapsMaxPathPoints);
  if (pts.length < 2) {
    final p = pts.first;
    return 'https://www.google.com/maps?q=${p.latitude.toStringAsFixed(6)},${p.longitude.toStringAsFixed(6)}';
  }
  final path = pts
      .map((p) => '${p.latitude.toStringAsFixed(6)},${p.longitude.toStringAsFixed(6)}')
      .join('|');
  return 'https://www.google.com/maps?path=color:0xff0088ff|weight:4|$path';
}

/// Evenly samples [points] down to at most [max] entries (keeps first + last).
List<LatLng> _downsample(List<LatLng> points, int max) {
  if (points.length <= max) return points;
  final out = <LatLng>[];
  for (var i = 0; i < max; i++) {
    final idx = (i * (points.length - 1)) / (max - 1);
    out.add(points[idx.round()]);
  }
  return out;
}
