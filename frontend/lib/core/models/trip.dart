part of models;

/// One GPS fix on a trip route (AUT-395). `t` epoch seconds, WGS84 degrees.
class GpsPoint {
  final int t;
  final double lat, lng;

  const GpsPoint(this.t, this.lat, this.lng);

  factory GpsPoint.fromJson(Map<String, dynamic> j) => GpsPoint(
        (j['t'] as num?)?.toInt() ?? 0,
        (j['lat'] as num?)?.toDouble() ?? 0,
        (j['lng'] as num?)?.toDouble() ?? 0,
      );
}

class LogEntry {
  final String id;
  final String? startedAt, endedAt;
  final int? startOdometerKm, endOdometerKm;
  final double? distanceKm;
  final String purpose; // work/private
  final String? reason;
  final String? startLocation, endLocation;
  final double? startLat, startLng, endLat, endLng;
  final String status; // in_progress/completed
  final List<GpsPoint> gpsSamples;

  const LogEntry({
    required this.id,
    this.startedAt,
    this.endedAt,
    this.startOdometerKm,
    this.endOdometerKm,
    this.distanceKm,
    this.purpose = 'private',
    this.reason,
    this.startLocation,
    this.endLocation,
    this.startLat,
    this.startLng,
    this.endLat,
    this.endLng,
    this.status = 'in_progress',
    this.gpsSamples = const [],
  });

  bool get isComplete => status == 'completed';
  bool get hasRoute => gpsSamples.length >= 2;

  factory LogEntry.fromJson(Map<String, dynamic> j) => LogEntry(
        id: j['id'] as String,
        startedAt: j['started_at'] as String?,
        endedAt: j['ended_at'] as String?,
        startOdometerKm: j['start_odometer_km'] as int?,
        endOdometerKm: j['end_odometer_km'] as int?,
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        purpose: j['purpose'] as String? ?? 'private',
        reason: j['reason'] as String?,
        startLocation: j['start_location'] as String?,
        endLocation: j['end_location'] as String?,
        startLat: (j['start_lat'] as num?)?.toDouble(),
        startLng: (j['start_lng'] as num?)?.toDouble(),
        endLat: (j['end_lat'] as num?)?.toDouble(),
        endLng: (j['end_lng'] as num?)?.toDouble(),
        status: j['status'] as String? ?? 'in_progress',
        gpsSamples: [
          for (final s in j['gps_samples'] as List? ?? const [])
            if (s is Map<String, dynamic>) GpsPoint.fromJson(s)
        ],
      );
}
