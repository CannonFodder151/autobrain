/// VASS (Vehicle Approval & Safety System) compliance API client (AUT-3668).
///
/// Thin wrapper over [ApiClient] mirroring the backend routes in
/// `backend/app/api/v1/vass.py` (AUT-3667). Screens never touch the wire
/// format; everything is decoded into the typed models in
/// `core/models/vass.dart`.
library;

import '../core/api_client.dart';
import '../core/models.dart';

class VassApi {
  VassApi(this._api);
  final ApiClient _api;

  // Pre-check wizard

  /// List pre-check sessions, optionally filtered by [vehicleId].
  Future<List<PrecheckOut>> listPrechecks({String? vehicleId}) async {
    final data = await _api.get(
      '/vass/prechecks',
      query: vehicleId != null ? {'vehicle_id': vehicleId} : null,
    ) as List;
    return data
        .map((e) => PrecheckOut.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Create a new pre-check session for [payload].
  Future<PrecheckOut> createPrecheck(PrecheckCreate payload) async {
    final data = await _api.post('/vass/prechecks', payload.toJson())
        as Map<String, dynamic>;
    return PrecheckOut.fromJson(data);
  }

  /// Fetch a single pre-check by [precheckId].
  Future<PrecheckOut> getPrecheck(String precheckId) async {
    final data = await _api.get('/vass/prechecks/$precheckId')
        as Map<String, dynamic>;
    return PrecheckOut.fromJson(data);
  }

  /// Patch a pre-check with the fields set on [payload].
  Future<PrecheckOut> updatePrecheck(
      String precheckId, PrecheckUpdate payload) async {
    final data = await _api.patch('/vass/prechecks/$precheckId', payload.toJson())
        as Map<String, dynamic>;
    return PrecheckOut.fromJson(data);
  }

  /// Delete a pre-check session.
  Future<void> deletePrecheck(String precheckId) =>
      _api.delete('/vass/prechecks/$precheckId');

  /// Run compliance checks and mark the pre-check as completed.
  Future<PrecheckOut> completePrecheck(String precheckId) async {
    final data = await _api.post('/vass/prechecks/$precheckId/complete')
        as Map<String, dynamic>;
    return PrecheckOut.fromJson(data);
  }

  // Compliance results

  /// Fetch per-modification compliance results for a pre-check.
  Future<List<ComplianceResultOut>> getComplianceResults(
      String precheckId) async {
    final data = await _api.get('/vass/prechecks/$precheckId/results') as List;
    return data
        .map((e) => ComplianceResultOut.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// GET variant of compliance aggregation.
  Future<ComplianceAggregationResponse> getComplianceAggregation(
      String precheckId) async {
    final data = await _api.get('/vass/compliance/aggregate/$precheckId')
        as Map<String, dynamic>;
    return ComplianceAggregationResponse.fromJson(data);
  }

  /// POST variant of compliance aggregation.
  Future<ComplianceAggregationResponse> aggregateCompliance(
      String precheckId) async {
    final data = await _api.post('/vass/compliance/aggregate', {
      'precheck_id': precheckId,
    }) as Map<String, dynamic>;
    return ComplianceAggregationResponse.fromJson(data);
  }

  // Compliance packs (PDF)

  /// List generated compliance packs for a pre-check.
  Future<List<CompliancePackOut>> listCompliancePacks(String precheckId) async {
    final data = await _api.get('/vass/prechecks/$precheckId/packs') as List;
    return data
        .map((e) => CompliancePackOut.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Generate a compliance pack PDF for a completed pre-check.
  Future<CompliancePackOut> generateCompliancePack(
      CompliancePackGenerateRequest request) async {
    final data = await _api
        .post('/vass/packs/generate', request.toJson())
        as Map<String, dynamic>;
    return CompliancePackOut.fromJson(data);
  }

  /// Download a compliance pack as raw PDF bytes.
  Future<List<int>> downloadCompliancePack(String packId) =>
      _api.export('/vass/packs/$packId/download');

  // Engineer marketplace

  /// Search engineers with the given [params].
  Future<EngineerSearchResponse> searchEngineers(
      [EngineerSearchParams? params]) async {
    final q = (params ?? const EngineerSearchParams()).toQuery();
    final data =
        await _api.get('/vass/engineers', query: q) as Map<String, dynamic>;
    return EngineerSearchResponse.fromJson(data);
  }

  /// Fetch a single engineer by [engineerId].
  Future<EngineerOut> getEngineer(String engineerId) async {
    final data =
        await _api.get('/vass/engineers/$engineerId') as Map<String, dynamic>;
    return EngineerOut.fromJson(data);
  }

  /// Create a new engineer record.
  Future<EngineerOut> createEngineer(EngineerCreate payload) async {
    final data = await _api.post('/vass/engineers', payload.toJson())
        as Map<String, dynamic>;
    return EngineerOut.fromJson(data);
  }

  /// Patch an engineer record.
  Future<EngineerOut> updateEngineer(
      String engineerId, EngineerUpdate payload) async {
    final data = await _api.patch('/vass/engineers/$engineerId', payload.toJson())
        as Map<String, dynamic>;
    return EngineerOut.fromJson(data);
  }

  // Engineer requests

  /// List the current user's engineer engagement requests.
  Future<List<EngineerRequestOut>> listEngineerRequests() async {
    final data = await _api.get('/vass/requests') as List;
    return data
        .map((e) => EngineerRequestOut.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Send an engagement request to an engineer.
  Future<EngineerRequestOut> createEngineerRequest(
      EngineerRequestCreate payload) async {
    final data = await _api.post('/vass/requests', payload.toJson())
        as Map<String, dynamic>;
    return EngineerRequestOut.fromJson(data);
  }

  // Import pathway

  /// Look up the import compliance pathway for a VIN.
  Future<ImportPathwayOut> createImportPathway(ImportPathwayRequest request) async {
    final data = await _api.post('/vass/import-pathway', request.toJson())
        as Map<String, dynamic>;
    return ImportPathwayOut.fromJson(data);
  }

  /// Fetch import pathway detail including document checklist.
  Future<ImportPathwayDetailOut> getImportPathway(String pathwayId) async {
    final data =
        await _api.get('/vass/import-pathway/$pathwayId') as Map<String, dynamic>;
    return ImportPathwayDetailOut.fromJson(data);
  }

  // VASS settings

  /// Fetch the user's VASS settings.
  Future<VassSettingsOut> getSettings() async {
    final data = await _api.get('/vass/settings') as Map<String, dynamic>;
    return VassSettingsOut.fromJson(data);
  }

  /// Update the user's VASS settings.
  Future<VassSettingsOut> updateSettings(VassSettingsUpdate payload) async {
    final data = await _api.patch('/vass/settings', payload.toJson())
        as Map<String, dynamic>;
    return VassSettingsOut.fromJson(data);
  }

  // Vehicle make/model/year lookup

  /// List all vehicle makes in the compliance database.
  Future<List<String>> listVehicleMakes() async {
    final data = await _api.get('/vass/vehicle-lookup/makes') as List;
    return data.map((e) => e as String).toList();
  }

  /// List available models for [make].
  Future<List<String>> listVehicleModels(String make) async {
    final data =
        await _api.get('/vass/vehicle-lookup/models/${Uri.encodeComponent(make)}') as List;
    return data.map((e) => e as String).toList();
  }

  /// Get the year range for a specific make/model.
  Future<Map<String, dynamic>> getVehicleYearRange(
      String make, String model) async {
    final data = await _api.get('/vass/vehicle-lookup/year-range', query: {
      'make': make,
      'model': model,
    }) as Map<String, dynamic>;
    return data;
  }

  /// Look up vehicles by make, model, and year.
  Future<VehicleLookupResponse> vehicleLookup(VehicleLookupRequest request) async {
    final data = await _api.post('/vass/vehicle-lookup', request.toJson())
        as Map<String, dynamic>;
    return VehicleLookupResponse.fromJson(data);
  }

  // VIN validation

  /// Validate a 17-character VIN.
  Future<VinValidationResponse> validateVin(String vin) async {
    final data = await _api.post('/vass/vin/validate', {'vin': vin})
        as Map<String, dynamic>;
    return VinValidationResponse.fromJson(data);
  }

  // Modification checklist

  /// Generate a compliance checklist for a set of modifications.
  Future<ModificationChecklistResponse> generateModificationChecklist(
      ModificationChecklistRequest request) async {
    final data = await _api
        .post('/vass/modification-checklist', request.toJson())
        as Map<String, dynamic>;
    return ModificationChecklistResponse.fromJson(data);
  }
}