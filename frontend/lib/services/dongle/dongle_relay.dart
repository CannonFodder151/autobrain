/// Relay of BLE-pulled dongle trips to the backend (AUT-1573).
///
/// When the phone syncs the dongle over BLE it also relays the pulled trips
/// to POST /devices/{id}/trips using the one-time device API key stored on
/// the phone — the same surface the firmware uses over WiFi. The server
/// dedupes on (device_id, device_trip_id), so relaying a trip the dongle
/// already uploaded over WiFi is a harmless no-op.
library;

import '../../core/api_client.dart';
import 'dongle_settings.dart';

class DongleRelayResult {
  final int accepted;
  final int duplicates;
  const DongleRelayResult({required this.accepted, required this.duplicates});
}

/// Converts one board trip CSV into the device-trips batch JSON object, or
/// null when the CSV carries no usable epoch rows. Mirrors the firmware's
/// upload_payload.h rules exactly so both paths produce identical payloads:
/// rows are "epoch,rpm,speed,coolant,throttle,lat,lon[,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode]", lat/lon degrees x10^7,
/// and "0,0" means no fix (dropped).
Map<String, dynamic>? tripCsvToJson(String filename, String csv) {
  if (!filename.endsWith('.csv')) return null;
  int? first, last;
  final samples = <Map<String, dynamic>>[];
  for (final line in csv.split('\n')) {
    final parts = line.trim().split(',');
    if (parts.length < 7) continue;
    final epoch = int.tryParse(parts[0].trim());
    if (epoch == null || epoch <= 0) continue;
    first ??= epoch;
    last = epoch;
    final lat = int.tryParse(parts[5].trim()) ?? 0;
    final lon = int.tryParse(parts[6].trim()) ?? 0;
    if (lat == 0 && lon == 0) continue;
    samples.add({
      't': epoch,
      'lat': lat / 1e7,
      'lon': lon / 1e7,
    });
  }
  if (first == null || last == null) return null;
  return {
    // Same deterministic id the firmware derives from its RTC stamp, so
    // BLE-relayed and WiFi-uploaded copies of one trip dedupe server-side.
    'device_trip_id': 'trip_${filename.substring(0, filename.length - 4)}',
    'started_at': _isoUtc(first),
    'ended_at': _isoUtc(last),
    'gps_samples': samples.isEmpty ? null : samples,
  };
}

/// Relays every convertible trip. Returns per-trip results; a trip that
/// fails to convert is skipped, an upload error aborts with the exception.
Future<DongleRelayResult> relayTrips(
  ApiClient api, {
  required String deviceId,
  required Map<String, String> trips,
}) async {
  final cfg = await DongleSettings.load();
  final apiKey = cfg.apiKey;
  if (apiKey == null || apiKey.isEmpty || cfg.deviceId != deviceId) {
    throw ApiException(401,
        'No device key stored for this dongle — re-link it in the OBD tab.');
  }
  final payload = <Map<String, dynamic>>[];
  for (final entry in trips.entries) {
    final obj = tripCsvToJson(entry.key, entry.value);
    if (obj != null) payload.add(obj);
  }
  if (payload.isEmpty)
    return const DongleRelayResult(accepted: 0, duplicates: 0);
  final data = await api.post(
    '/devices/$deviceId/trips',
    {'trips': payload},
    {'X-Device-API-Key': apiKey},
  ) as Map<String, dynamic>;
  return DongleRelayResult(
    accepted: (data['accepted'] as num?)?.toInt() ?? 0,
    duplicates: (data['duplicates'] as num?)?.toInt() ?? 0,
  );
}

String _isoUtc(int epochSeconds) => DateTime.fromMillisecondsSinceEpoch(
      epochSeconds * 1000,
      isUtc: true,
    ).toIso8601String();

// ponytail: jsonEncode not needed for keys we build ourselves; keep the map
// literal so ApiClient encodes it. Swap to manual JSON only if ApiClient
// ever grows header-free raw-body needs.
