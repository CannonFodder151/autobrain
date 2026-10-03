import 'dart:convert';

import '../../core/api_client.dart';
import '../../core/models.dart';

/// VASS (Vehicle Approval & Safety System) API service.
///
/// All methods are thin wrappers around [ApiClient] — no AI, purely deterministic
/// calls to the backend rule engine.
class VassApi {
  VassApi(this.api);

  final ApiClient api;

  // ------------------------------------------------------------------
  // Pre-checks
  // ------------------------------------------------------------------

  Future<List<VassPrecheck>> listPrechecks([String? vehicleId]) async {
    final query = vehicleId != null ? {'vehicle_id': vehicleId} : null;
    final data = await api.get('/vass/prechecks', query: query) as List;
    return data.map((e) => VassPrecheck.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<VassPrecheck> createPrecheck({
    required String vehicleId,
    required VassJurisdiction jurisdiction,
    List<ModificationSelection> modifications = const [],
    String? vin,
    String? make,
    String? model,
    int? year,
    String? bodyType,
    String? engine,
    String? transmission,
  }) async {
    final body = {
      'vehicle_id': vehicleId,
      'jurisdiction': jurisdiction.name,
      'modifications': modifications.map((m) => m.toJson()).toList(),
      if (vin != null) 'vin': vin,
      if (make != null) 'make': make,
      if (model != null) 'model': model,
      if (year != null) 'year': year,
      if (bodyType != null) 'body_type': bodyType,
      if (engine != null) 'engine': engine,
      if (transmission != null) 'transmission': transmission,
    };
    final data = await api.post('/vass/prechecks', body) as Map<String, dynamic>;
    return VassPrecheck.fromJson(data);
  }

  Future<VassPrecheck> getPrecheck(String precheckId) async {
    final data = await api.get('/vass/prechecks/$precheckId') as Map<String, dynamic>;
    return VassPrecheck.fromJson(data);
  }

  Future<VassPrecheck> updatePrecheck(
    String precheckId, {
    VassJurisdiction? jurisdiction,
    String? vin,
    String? make,
    String? model,
    int? year,
    String? bodyType,
    String? engine,
    String? transmission,
    List<ModificationSelection>? modifications,
    VassPrecheckStatus? status,
  }) async {
    final body = <String, dynamic>{};
    if (jurisdiction != null) body['jurisdiction'] = jurisdiction.name;
    if (vin != null) body['vin'] = vin;
    if (make != null) body['make'] = make;
    if (model != null) body['model'] = model;
    if (year != null) body['year'] = year;
    if (bodyType != null) body['body_type'] = bodyType;
    if (engine != null) body['engine'] = engine;
    if (transmission != null) body['transmission'] = transmission;
    if (modifications != null) {
      body['modifications'] = modifications.map((m) => m.toJson()).toList();
    }
    if (status != null) body['status'] = status.name;
    final data = await api.patch('/vass/prechecks/$precheckId', body) as Map<String, dynamic>;
    return VassPrecheck.fromJson(data);
  }

  Future<void> deletePrecheck(String precheckId) async {
    await api.delete('/vass/prechecks/$precheckId');
  }

  Future<VassPrecheck> completePrecheck(String precheckId) async {
    final data = await api.post('/vass/prechecks/$precheckId/complete') as Map<String, dynamic>;
    return VassPrecheck.fromJson(data);
  }

  Future<List<VassComplianceResult>> getComplianceResults(String precheckId) async {
    final data = await api.get('/vass/prechecks/$precheckId/results') as List;
    return data.map((e) => VassComplianceResult.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ------------------------------------------------------------------
  // Compliance Packs
  // ------------------------------------------------------------------

  Future<List<CompliancePack>> listPacks(String precheckId) async {
    final data = await api.get('/vass/prechecks/$precheckId/packs') as List;
    return data.map((e) => CompliancePack.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<CompliancePack> generatePack(String precheckId) async {
    final data = await api.post('/vass/packs/generate', {'precheck_id': precheckId}) as Map<String, dynamic>;
    return CompliancePack.fromJson(data);
  }

  Future<List<int>> downloadPack(String packId) async {
    return await api.export('/vass/packs/$packId/download');
  }

  // ------------------------------------------------------------------
  // Engineers
  // ------------------------------------------------------------------

  Future<List<VassEngineer>> searchEngineers({
    VassJurisdiction? jurisdiction,
    String? engineerType,
    String? specialisation,
    String? suburb,
    String? postcode,
    double? minRating,
    bool isActive = true,
    int page = 1,
    int pageSize = 20,
  }) async {
    final query = <String, String>{
      'page': page.toString(),
      'page_size': pageSize.toString(),
      'is_active': isActive.toString(),
    };
    if (jurisdiction != null) query['jurisdiction'] = jurisdiction.name;
    if (engineerType != null) query['engineer_type'] = engineerType;
    if (specialisation != null) query['specialisation'] = specialisation;
    if (suburb != null) query['suburb'] = suburb;
    if (postcode != null) query['postcode'] = postcode;
    if (minRating != null) query['min_rating'] = minRating.toString();

    final data = await api.get('/vass/engineers', query: query) as Map<String, dynamic>;
    final list = (data['engineers'] as List).cast<Map<String, dynamic>>();
    return list.map(VassEngineer.fromJson).toList();
  }

  Future<VassEngineer?> getEngineer(String engineerId) async {
    final data = await api.get('/vass/engineers/$engineerId') as Map<String, dynamic>;
    return VassEngineer.fromJson(data);
  }

  Future<void> requestEngineer({
    required String engineerId,
    String? vehicleId,
    String? precheckId,
    String? message,
  }) async {
    final body = <String, dynamic>{'engineer_id': engineerId};
    if (vehicleId != null) body['vehicle_id'] = vehicleId;
    if (precheckId != null) body['precheck_id'] = precheckId;
    if (message != null) body['message'] = message;
    await api.post('/vass/requests', body);
  }

  // ------------------------------------------------------------------
  // Import Pathway
  // ------------------------------------------------------------------

  Future<ImportPathway> lookupImportPathway(String vin, VassJurisdiction jurisdiction) async {
    final body = {'vin': vin, 'jurisdiction': jurisdiction.name};
    final data = await api.post('/vass/import-pathway', body) as Map<String, dynamic>;
    return ImportPathway.fromJson(data);
  }

  Future<ImportPathway> getImportPathway(String pathwayId) async {
    final data = await api.get('/vass/import-pathway/$pathwayId') as Map<String, dynamic>;
    return ImportPathway.fromJson(data);
  }

  // ------------------------------------------------------------------
  // Settings
  // ------------------------------------------------------------------

  Future<VassJurisdiction> getDefaultJurisdiction() async {
    final data = await api.get('/vass/settings') as Map<String, dynamic>;
    return VassJurisdiction.fromString(data['default_jurisdiction'] as String?) ?? VassJurisdiction.VIC;
  }

  Future<VassJurisdiction> updateDefaultJurisdiction(VassJurisdiction jurisdiction) async {
    final data = await api.patch('/vass/settings', {'default_jurisdiction': jurisdiction.name}) as Map<String, dynamic>;
    return VassJurisdiction.fromString(data['default_jurisdiction'] as String?) ?? VassJurisdiction.VIC;
  }
}
