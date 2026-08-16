/// Dongle device API — user-scoped device management (AUT-918/AUT-936).
///
/// The dongle upload surface (POST /devices/{id}/trips) is firmware-only and
/// authenticated by X-Device-API-Key; the app never calls it. The app only
/// creates devices (to receive the one-time key) and lists them (for
/// last_seen_at status + reuse).
library;

import '../../core/api_client.dart';

class DongleDevice {
  final String id;
  final String name;
  final String? vehicleId;
  final DateTime? lastSeenAt;
  final DateTime? createdAt;

  /// Set only on the create response; the server never returns it again.
  final String? oneTimeApiKey;

  const DongleDevice({
    required this.id,
    required this.name,
    this.vehicleId,
    this.lastSeenAt,
    this.createdAt,
    this.oneTimeApiKey,
  });

  factory DongleDevice.fromJson(Map<String, dynamic> j) => DongleDevice(
        id: j['id'] as String,
        name: (j['name'] as String?) ?? 'AutoBrain dongle',
        vehicleId: j['vehicle_id'] as String?,
        lastSeenAt: DateTime.tryParse((j['last_seen_at'] as String?) ?? ''),
        createdAt: DateTime.tryParse((j['created_at'] as String?) ?? ''),
        oneTimeApiKey: j['api_key'] as String?,
      );
}

class DongleApi {
  DongleApi(this.api);
  final ApiClient api;

  /// Lists my devices (the server never returns the plaintext key here).
  Future<List<DongleDevice>> list() async {
    final data = await api.get('/devices') as List;
    return data
        .map((e) => DongleDevice.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Creates a dongle device. [oneTimeApiKey] is returned ONLY here — the
  /// server stores a hash, so show it once and tell the user to save it.
  Future<DongleDevice> create({
    required String name,
    String? vehicleId,
  }) async {
    final data = await api.post('/devices', {
      'name': name,
      if (vehicleId != null) 'vehicle_id': vehicleId,
    }) as Map<String, dynamic>;
    return DongleDevice.fromJson(data);
  }
}
