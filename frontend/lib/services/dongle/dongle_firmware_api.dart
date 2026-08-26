/// Dongle firmware manifest API — app-side model for the BLE OTA flow (AUT-1673).
///
/// The OTA bytes themselves never travel through this API: the app downloads
/// them from the short-lived signed URL the manifest returns, verifies SHA-256,
/// and chunk-writes the verified bytes over BLE. This keeps the API tiny
/// (manifest + telemetry only) and means re-publishing firmware never touches
/// the app — only MinIO + this manifest row.
library;

import '../../core/api_client.dart';

class DongleFirmwareVersion {
  const DongleFirmwareVersion({
    required this.model,
    required this.version,
    required this.sha256,
    required this.sizeBytes,
    required this.blobUrl,
    this.releaseNotes,
  });

  final String model;
  final String version;
  final String sha256;
  final int sizeBytes;
  final String blobUrl;
  final String? releaseNotes;

  factory DongleFirmwareVersion.fromJson(Map<String, dynamic> j) =>
      DongleFirmwareVersion(
        model: j['model'] as String,
        version: j['version'] as String,
        sha256: j['sha256'] as String,
        sizeBytes: (j['size_bytes'] as num).toInt(),
        blobUrl: j['blob_url'] as String,
        releaseNotes: j['release_notes'] as String?,
      );
}

class DongleInstalledFirmware {
  const DongleInstalledFirmware({
    required this.model,
    required this.firmwareVersion,
    required this.serialNumber,
    required this.lastReportedAt,
  });

  final String model;
  final String firmwareVersion;
  final String serialNumber;
  final DateTime lastReportedAt;

  factory DongleInstalledFirmware.fromJson(Map<String, dynamic> j) =>
      DongleInstalledFirmware(
        model: j['model'] as String,
        firmwareVersion: j['firmware_version'] as String,
        serialNumber: j['serial_number'] as String,
        lastReportedAt:
            DateTime.parse(j['last_reported_at'] as String).toLocal(),
      );
}

class DongleFirmwareApi {
  DongleFirmwareApi(this.api);
  final ApiClient api;

  /// Latest manifest for [model], or null when no release has been published yet.
  Future<DongleFirmwareVersion?> latest(String model) async {
    final data = await api.get(
      '/dongle/firmware/latest',
      query: {'model': model},
    );
    if (data == null) return null;
    return DongleFirmwareVersion.fromJson(data as Map<String, dynamic>);
  }

  /// Installed firmware for the device whose [deviceId] is the ``Device.id``
  /// UUID returned by ``GET /devices`` (NOT the BLE hardware serial — that is
  /// only written via [/report]). The server does a primary-key lookup on this
  /// value, so the app↔server mapping is exact: a mismatched UUID yields 404.
  Future<DongleInstalledFirmware?> installed(String deviceId) async {
    final data = await api.get(
      '/dongle/firmware/installed',
      query: {'device_id': deviceId},
    );
    if (data == null) return null;
    return DongleInstalledFirmware.fromJson(data as Map<String, dynamic>);
  }
}
