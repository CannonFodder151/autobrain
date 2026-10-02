part of models;

enum VassJurisdiction {
  VIC('VIC'),
  NSW('NSW'),
  QLD('QLD'),
  SA('SA'),
  WA('WA'),
  TAS('TAS'),
  ACT('ACT'),
  NT('NT');

  const VassJurisdiction(this.value);
  final String value;

  static VassJurisdiction fromString(String s) {
    return VassJurisdiction.values.firstWhere(
      (e) => e.value == s,
      orElse: () => VassJurisdiction.VIC,
    );
  }

  @override
  String toString() => value;
}

enum ComplianceStatus {
  pass('pass'),
  fail('fail'),
  conditional('conditional'),
  pending('pending'),
  na('na');

  const ComplianceStatus(this.value);
  final String value;

  static ComplianceStatus fromString(String s) {
    return ComplianceStatus.values.firstWhere(
      (e) => e.value == s,
      orElse: () => ComplianceStatus.pending,
    );
  }

  @override
  String toString() => value;
}

enum PrecheckStatus {
  draft('draft'),
  inProgress('in_progress'),
  completed('completed'),
  archived('archived');

  const PrecheckStatus(this.value);
  final String value;

  static PrecheckStatus fromString(String s) {
    return PrecheckStatus.values.firstWhere(
      (e) => e.value == s,
      orElse: () => PrecheckStatus.draft,
    );
  }

  @override
  String toString() => value;
}

enum EngineerType {
  signatory('signatory'),
  inspector('inspector'),
  consultant('consultant');

  const EngineerType(this.value);
  final String value;

  static EngineerType fromString(String s) {
    return EngineerType.values.firstWhere(
      (e) => e.value == s,
      orElse: () => EngineerType.signatory,
    );
  }

  @override
  String toString() => value;
}

class ModificationSelection {
  final String name;
  final String category;
  final String? brand;
  final String? notes;

  const ModificationSelection({
    required this.name,
    required this.category,
    this.brand,
    this.notes,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'category': category,
        if (brand != null) 'brand': brand,
        if (notes != null) 'notes': notes,
      };

  factory ModificationSelection.fromJson(Map<String, dynamic> json) {
    return ModificationSelection(
      name: json['name'] as String,
      category: json['category'] as String,
      brand: json['brand'] as String?,
      notes: json['notes'] as String?,
    );
  }
}

class PrecheckCreate {
  final String vehicleId;
  final VassJurisdiction jurisdiction;
  final String? vin;
  final String? make;
  final String? model;
  final int? year;
  final String? bodyType;
  final String? engine;
  final String? transmission;
  final List<ModificationSelection> modifications;

  const PrecheckCreate({
    required this.vehicleId,
    this.jurisdiction = VassJurisdiction.VIC,
    this.vin,
    this.make,
    this.model,
    this.year,
    this.bodyType,
    this.engine,
    this.transmission,
    this.modifications = const [],
  });

  Map<String, dynamic> toJson() => {
        'vehicle_id': vehicleId,
        'jurisdiction': jurisdiction.value,
        if (vin != null) 'vin': vin,
        if (make != null) 'make': make,
        if (model != null) 'model': model,
        if (year != null) 'year': year,
        if (bodyType != null) 'body_type': bodyType,
        if (engine != null) 'engine': engine,
        if (transmission != null) 'transmission': transmission,
        'modifications': modifications.map((m) => m.toJson()).toList(),
      };
}

class PrecheckUpdate {
  final VassJurisdiction? jurisdiction;
  final String? vin;
  final String? make;
  final String? model;
  final int? year;
  final String? bodyType;
  final String? engine;
  final String? transmission;
  final List<ModificationSelection>? modifications;
  final PrecheckStatus? status;

  const PrecheckUpdate({
    this.jurisdiction,
    this.vin,
    this.make,
    this.model,
    this.year,
    this.bodyType,
    this.engine,
    this.transmission,
    this.modifications,
    this.status,
  });

  Map<String, dynamic> toJson() => {
        if (jurisdiction != null) 'jurisdiction': jurisdiction!.value,
        if (vin != null) 'vin': vin,
        if (make != null) 'make': make,
        if (model != null) 'model': model,
        if (year != null) 'year': year,
        if (bodyType != null) 'body_type': bodyType,
        if (engine != null) 'engine': engine,
        if (transmission != null) 'transmission': transmission,
        if (modifications != null)
          'modifications': modifications!.map((m) => m.toJson()).toList(),
        if (status != null) 'status': status!.value,
      };
}

class PrecheckOut {
  final String id;
  final String vehicleId;
  final String userId;
  final VassJurisdiction jurisdiction;
  final PrecheckStatus status;
  final String? vin;
  final String? make;
  final String? model;
  final int? year;
  final String? bodyType;
  final String? engine;
  final String? transmission;
  final List<ModificationSelection> modifications;
  final DateTime? completedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  const PrecheckOut({
    required this.id,
    required this.vehicleId,
    required this.userId,
    required this.jurisdiction,
    required this.status,
    this.vin,
    this.make,
    this.model,
    this.year,
    this.bodyType,
    this.engine,
    this.transmission,
    this.modifications = const [],
    this.completedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  factory PrecheckOut.fromJson(Map<String, dynamic> json) {
    return PrecheckOut(
      id: json['id'] as String,
      vehicleId: json['vehicle_id'] as String,
      userId: json['user_id'] as String,
      jurisdiction: VassJurisdiction.fromString(json['jurisdiction'] as String),
      status: PrecheckStatus.fromString(json['status'] as String),
      vin: json['vin'] as String?,
      make: json['make'] as String?,
      model: json['model'] as String?,
      year: json['year'] as int?,
      bodyType: json['body_type'] as String?,
      engine: json['engine'] as String?,
      transmission: json['transmission'] as String?,
      modifications: (json['modifications'] as List? ?? [])
          .map((e) => ModificationSelection.fromJson(e as Map<String, dynamic>))
          .toList(),
      completedAt: json['completed_at'] != null
          ? DateTime.parse(json['completed_at'] as String)
          : null,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class ComplianceResultOut {
  final String id;
  final String precheckId;
  final String modificationName;
  final String category;
  final ComplianceStatus status;
  final List<String> adrReferences;
  final List<String> vsbReferences;
  final List<String> vsb6References;
  final String? notes;
  final String? conditionalDetails;
  final DateTime createdAt;

  const ComplianceResultOut({
    required this.id,
    required this.precheckId,
    required this.modificationName,
    required this.category,
    required this.status,
    this.adrReferences = const [],
    this.vsbReferences = const [],
    this.vsb6References = const [],
    this.notes,
    this.conditionalDetails,
    required this.createdAt,
  });

  factory ComplianceResultOut.fromJson(Map<String, dynamic> json) {
    return ComplianceResultOut(
      id: json['id'] as String,
      precheckId: json['precheck_id'] as String,
      modificationName: json['modification_name'] as String,
      category: json['category'] as String,
      status: ComplianceStatus.fromString(json['status'] as String),
      adrReferences: (json['adr_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      vsbReferences: (json['vsb_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      vsb6References: (json['vsb6_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      notes: json['notes'] as String?,
      conditionalDetails: json['conditional_details'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class EngineerCreate {
  final VassJurisdiction jurisdiction;
  final EngineerType engineerType;
  final String name;
  final String? businessName;
  final String? abn;
  final String? email;
  final String? phone;
  final String? address;
  final String? suburb;
  final String? postcode;
  final List<String> specialisations;
  final String? licenseNumber;
  final DateTime? licenseExpiry;

  const EngineerCreate({
    required this.jurisdiction,
    this.engineerType = EngineerType.signatory,
    required this.name,
    this.businessName,
    this.abn,
    this.email,
    this.phone,
    this.address,
    this.suburb,
    this.postcode,
    this.specialisations = const [],
    this.licenseNumber,
    this.licenseExpiry,
  });

  Map<String, dynamic> toJson() => {
        'jurisdiction': jurisdiction.value,
        'engineer_type': engineerType.value,
        'name': name,
        if (businessName != null) 'business_name': businessName,
        if (abn != null) 'abn': abn,
        if (email != null) 'email': email,
        if (phone != null) 'phone': phone,
        if (address != null) 'address': address,
        if (suburb != null) 'suburb': suburb,
        if (postcode != null) 'postcode': postcode,
        'specialisations': specialisations,
        if (licenseNumber != null) 'license_number': licenseNumber,
        if (licenseExpiry != null)
          'license_expiry':
              '${licenseExpiry!.year.toString().padLeft(4, '0')}-${licenseExpiry!.month.toString().padLeft(2, '0')}-${licenseExpiry!.day.toString().padLeft(2, '0')}',
      };
}

class EngineerUpdate {
  final EngineerType? engineerType;
  final String? name;
  final String? businessName;
  final String? abn;
  final String? email;
  final String? phone;
  final String? address;
  final String? suburb;
  final String? postcode;
  final List<String>? specialisations;
  final String? licenseNumber;
  final DateTime? licenseExpiry;
  final bool? isActive;

  const EngineerUpdate({
    this.engineerType,
    this.name,
    this.businessName,
    this.abn,
    this.email,
    this.phone,
    this.address,
    this.suburb,
    this.postcode,
    this.specialisations,
    this.licenseNumber,
    this.licenseExpiry,
    this.isActive,
  });

  Map<String, dynamic> toJson() => {
        if (engineerType != null) 'engineer_type': engineerType!.value,
        if (name != null) 'name': name,
        if (businessName != null) 'business_name': businessName,
        if (abn != null) 'abn': abn,
        if (email != null) 'email': email,
        if (phone != null) 'phone': phone,
        if (address != null) 'address': address,
        if (suburb != null) 'suburb': suburb,
        if (postcode != null) 'postcode': postcode,
        if (specialisations != null) 'specialisations': specialisations,
        if (licenseNumber != null) 'license_number': licenseNumber,
        if (licenseExpiry != null)
          'license_expiry':
              '${licenseExpiry!.year.toString().padLeft(4, '0')}-${licenseExpiry!.month.toString().padLeft(2, '0')}-${licenseExpiry!.day.toString().padLeft(2, '0')}',
        if (isActive != null) 'is_active': isActive,
      };
}

class EngineerOut {
  final String id;
  final VassJurisdiction jurisdiction;
  final EngineerType engineerType;
  final String name;
  final String? businessName;
  final String? abn;
  final String? email;
  final String? phone;
  final String? address;
  final String? suburb;
  final String? postcode;
  final List<String> specialisations;
  final String? licenseNumber;
  final DateTime? licenseExpiry;
  final bool isActive;
  final double? rating;
  final int reviewCount;
  final DateTime createdAt;
  final DateTime updatedAt;

  const EngineerOut({
    required this.id,
    required this.jurisdiction,
    required this.engineerType,
    required this.name,
    this.businessName,
    this.abn,
    this.email,
    this.phone,
    this.address,
    this.suburb,
    this.postcode,
    this.specialisations = const [],
    this.licenseNumber,
    this.licenseExpiry,
    required this.isActive,
    this.rating,
    required this.reviewCount,
    required this.createdAt,
    required this.updatedAt,
  });

  factory EngineerOut.fromJson(Map<String, dynamic> json) {
    return EngineerOut(
      id: json['id'] as String,
      jurisdiction: VassJurisdiction.fromString(json['jurisdiction'] as String),
      engineerType: EngineerType.fromString(json['engineer_type'] as String),
      name: json['name'] as String,
      businessName: json['business_name'] as String?,
      abn: json['abn'] as String?,
      email: json['email'] as String?,
      phone: json['phone'] as String?,
      address: json['address'] as String?,
      suburb: json['suburb'] as String?,
      postcode: json['postcode'] as String?,
      specialisations: (json['specialisations'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      licenseNumber: json['license_number'] as String?,
      licenseExpiry: json['license_expiry'] != null
          ? DateTime.parse(json['license_expiry'] as String)
          : null,
      isActive: (json['is_active'] as bool?) ?? true,
      rating: (json['rating'] as num?)?.toDouble(),
      reviewCount: (json['review_count'] as int?) ?? 0,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class EngineerSearchParams {
  final VassJurisdiction? jurisdiction;
  final EngineerType? engineerType;
  final String? specialisation;
  final String? suburb;
  final String? postcode;
  final double? minRating;
  final bool isActive;
  final int page;
  final int pageSize;

  const EngineerSearchParams({
    this.jurisdiction,
    this.engineerType,
    this.specialisation,
    this.suburb,
    this.postcode,
    this.minRating,
    this.isActive = true,
    this.page = 1,
    this.pageSize = 20,
  });

  Map<String, String> toQuery() {
    final q = <String, String>{};
    if (jurisdiction != null) q['jurisdiction'] = jurisdiction!.value;
    if (engineerType != null) q['engineer_type'] = engineerType!.value;
    if (specialisation != null) q['specialisation'] = specialisation!;
    if (suburb != null) q['suburb'] = suburb!;
    if (postcode != null) q['postcode'] = postcode!;
    if (minRating != null) q['min_rating'] = minRating!.toString();
    q['is_active'] = isActive.toString();
    q['page'] = page.toString();
    q['page_size'] = pageSize.toString();
    return q;
  }
}

class EngineerSearchResponse {
  final List<EngineerOut> engineers;
  final int total;
  final int page;
  final int pageSize;
  final int totalPages;

  const EngineerSearchResponse({
    required this.engineers,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.totalPages,
  });

  factory EngineerSearchResponse.fromJson(Map<String, dynamic> json) {
    return EngineerSearchResponse(
      engineers: (json['engineers'] as List? ?? [])
          .map((e) => EngineerOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int? ?? 0,
      page: json['page'] as int? ?? 1,
      pageSize: json['page_size'] as int? ?? 20,
      totalPages: json['total_pages'] as int? ?? 1,
    );
  }
}

class EngineerRequestCreate {
  final String engineerId;
  final String? vehicleId;
  final String? precheckId;
  final String? message;

  const EngineerRequestCreate({
    required this.engineerId,
    this.vehicleId,
    this.precheckId,
    this.message,
  });

  Map<String, dynamic> toJson() => {
        'engineer_id': engineerId,
        if (vehicleId != null) 'vehicle_id': vehicleId,
        if (precheckId != null) 'precheck_id': precheckId,
        if (message != null) 'message': message,
      };
}

class EngineerRequestOut {
  final String id;
  final String engineerId;
  final String userId;
  final String? vehicleId;
  final String? precheckId;
  final String? message;
  final String status;
  final double? quotedAmount;
  final DateTime createdAt;
  final DateTime updatedAt;

  const EngineerRequestOut({
    required this.id,
    required this.engineerId,
    required this.userId,
    this.vehicleId,
    this.precheckId,
    this.message,
    required this.status,
    this.quotedAmount,
    required this.createdAt,
    required this.updatedAt,
  });

  factory EngineerRequestOut.fromJson(Map<String, dynamic> json) {
    return EngineerRequestOut(
      id: json['id'] as String,
      engineerId: json['engineer_id'] as String,
      userId: json['user_id'] as String,
      vehicleId: json['vehicle_id'] as String?,
      precheckId: json['precheck_id'] as String?,
      message: json['message'] as String?,
      status: json['status'] as String? ?? 'pending',
      quotedAmount: (json['quoted_amount'] as num?)?.toDouble(),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class ImportPathwayRequest {
  final String vin;
  final VassJurisdiction jurisdiction;

  const ImportPathwayRequest({
    required this.vin,
    this.jurisdiction = VassJurisdiction.VIC,
  });

  Map<String, dynamic> toJson() => {
        'vin': vin,
        'jurisdiction': jurisdiction.value,
      };
}

class ImportPathwayOut {
  final String id;
  final String vin;
  final VassJurisdiction jurisdiction;
  final String? vehicleMake;
  final String? vehicleModel;
  final int? vehicleYear;
  final String pathwayType;
  final String eligibility;
  final Map<String, dynamic>? requirements;
  final List<String> adrRequirements;
  final DateTime createdAt;
  final DateTime updatedAt;

  const ImportPathwayOut({
    required this.id,
    required this.vin,
    required this.jurisdiction,
    this.vehicleMake,
    this.vehicleModel,
    this.vehicleYear,
    required this.pathwayType,
    required this.eligibility,
    this.requirements,
    this.adrRequirements = const [],
    required this.createdAt,
    required this.updatedAt,
  });

  factory ImportPathwayOut.fromJson(Map<String, dynamic> json) {
    return ImportPathwayOut(
      id: json['id'] as String,
      vin: json['vin'] as String,
      jurisdiction: VassJurisdiction.fromString(json['jurisdiction'] as String),
      vehicleMake: json['vehicle_make'] as String?,
      vehicleModel: json['vehicle_model'] as String?,
      vehicleYear: json['vehicle_year'] as int?,
      pathwayType: json['pathway_type'] as String? ?? '',
      eligibility: json['eligibility'] as String? ?? '',
      requirements: json['requirements'] as Map<String, dynamic>?,
      adrRequirements: (json['adr_requirements'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class DocumentChecklistItem {
  final String name;
  final String? description;
  final bool required;
  final bool provided;
  final String? notes;

  const DocumentChecklistItem({
    required this.name,
    this.description,
    this.required = true,
    this.provided = false,
    this.notes,
  });

  factory DocumentChecklistItem.fromJson(Map<String, dynamic> json) {
    return DocumentChecklistItem(
      name: json['name'] as String,
      description: json['description'] as String?,
      required: (json['required'] as bool?) ?? true,
      provided: (json['provided'] as bool?) ?? false,
      notes: json['notes'] as String?,
    );
  }
}

class ImportPathwayDetailOut extends ImportPathwayOut {
  final List<DocumentChecklistItem> documentChecklist;

  const ImportPathwayDetailOut({
    required super.id,
    required super.vin,
    required super.jurisdiction,
    super.vehicleMake,
    super.vehicleModel,
    super.vehicleYear,
    required super.pathwayType,
    required super.eligibility,
    super.requirements,
    super.adrRequirements,
    required super.createdAt,
    required super.updatedAt,
    this.documentChecklist = const [],
  });

  factory ImportPathwayDetailOut.fromJson(Map<String, dynamic> json) {
    final base = ImportPathwayOut.fromJson(json);
    return ImportPathwayDetailOut(
      id: base.id,
      vin: base.vin,
      jurisdiction: base.jurisdiction,
      vehicleMake: base.vehicleMake,
      vehicleModel: base.vehicleModel,
      vehicleYear: base.vehicleYear,
      pathwayType: base.pathwayType,
      eligibility: base.eligibility,
      requirements: base.requirements,
      adrRequirements: base.adrRequirements,
      createdAt: base.createdAt,
      updatedAt: base.updatedAt,
      documentChecklist: (json['document_checklist'] as List? ?? [])
          .map((e) => DocumentChecklistItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class CompliancePackOut {
  final String id;
  final String precheckId;
  final String filename;
  final int fileSize;
  final double? overallScore;
  final int totalMods;
  final int passedMods;
  final int failedMods;
  final int conditionalMods;
  final DateTime createdAt;

  const CompliancePackOut({
    required this.id,
    required this.precheckId,
    required this.filename,
    required this.fileSize,
    this.overallScore,
    required this.totalMods,
    required this.passedMods,
    required this.failedMods,
    required this.conditionalMods,
    required this.createdAt,
  });

  factory CompliancePackOut.fromJson(Map<String, dynamic> json) {
    return CompliancePackOut(
      id: json['id'] as String,
      precheckId: json['precheck_id'] as String,
      filename: json['filename'] as String,
      fileSize: json['file_size'] as int? ?? 0,
      overallScore: (json['overall_score'] as num?)?.toDouble(),
      totalMods: json['total_mods'] as int? ?? 0,
      passedMods: json['passed_mods'] as int? ?? 0,
      failedMods: json['failed_mods'] as int? ?? 0,
      conditionalMods: json['conditional_mods'] as int? ?? 0,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class CompliancePackGenerateRequest {
  final String precheckId;
  final bool includeImages;

  const CompliancePackGenerateRequest({
    required this.precheckId,
    this.includeImages = false,
  });

  Map<String, dynamic> toJson() => {
        'precheck_id': precheckId,
        'include_images': includeImages,
      };
}

class VassSettingsOut {
  final VassJurisdiction defaultJurisdiction;
  final List<VassJurisdiction> availableJurisdictions;

  const VassSettingsOut({
    this.defaultJurisdiction = VassJurisdiction.VIC,
    this.availableJurisdictions = const [
      VassJurisdiction.VIC,
      VassJurisdiction.NSW,
      VassJurisdiction.QLD,
      VassJurisdiction.SA,
      VassJurisdiction.WA,
      VassJurisdiction.TAS,
      VassJurisdiction.ACT,
      VassJurisdiction.NT,
    ],
  });

  factory VassSettingsOut.fromJson(Map<String, dynamic> json) {
    return VassSettingsOut(
      defaultJurisdiction: VassJurisdiction.fromString(
          json['default_jurisdiction'] as String? ?? 'VIC'),
      availableJurisdictions: (json['available_jurisdictions'] as List? ?? [])
          .map((e) => VassJurisdiction.fromString(e as String))
          .toList(),
    );
  }
}

class VassSettingsUpdate {
  final VassJurisdiction? defaultJurisdiction;

  const VassSettingsUpdate({this.defaultJurisdiction});

  Map<String, dynamic> toJson() => {
        if (defaultJurisdiction != null)
          'default_jurisdiction': defaultJurisdiction!.value,
      };
}

class VehicleLookupRequest {
  final String make;
  final String? model;
  final int? year;

  const VehicleLookupRequest({
    required this.make,
    this.model,
    this.year,
  });

  Map<String, dynamic> toJson() => {
        'make': make,
        if (model != null) 'model': model,
        if (year != null) 'year': year,
      };
}

class VehicleLookupItem {
  final String make;
  final String model;
  final int yearFrom;
  final int yearTo;
  final String category;
  final bool rhd;

  const VehicleLookupItem({
    required this.make,
    required this.model,
    required this.yearFrom,
    required this.yearTo,
    required this.category,
    required this.rhd,
  });

  factory VehicleLookupItem.fromJson(Map<String, dynamic> json) {
    return VehicleLookupItem(
      make: json['make'] as String,
      model: json['model'] as String,
      yearFrom: json['year_from'] as int,
      yearTo: json['year_to'] as int,
      category: json['category'] as String,
      rhd: (json['rhd'] as bool?) ?? true,
    );
  }
}

class VehicleLookupResponse {
  final List<VehicleLookupItem> vehicles;
  final int total;
  final String make;
  final String? model;
  final int? year;

  const VehicleLookupResponse({
    required this.vehicles,
    required this.total,
    required this.make,
    this.model,
    this.year,
  });

  factory VehicleLookupResponse.fromJson(Map<String, dynamic> json) {
    return VehicleLookupResponse(
      vehicles: (json['vehicles'] as List? ?? [])
          .map((e) => VehicleLookupItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int? ?? 0,
      make: json['make'] as String,
      model: json['model'] as String?,
      year: json['year'] as int?,
    );
  }
}

class VinValidationRequest {
  final String vin;

  const VinValidationRequest({required this.vin});

  Map<String, dynamic> toJson() => {'vin': vin};
}

class VinValidationResponse {
  final String vin;
  final bool isValid;
  final List<String> errors;
  final bool? checkDigitValid;
  final String? manufacturer;
  final String? country;
  final int? year;
  final bool? isRightHandDrive;

  const VinValidationResponse({
    required this.vin,
    required this.isValid,
    this.errors = const [],
    this.checkDigitValid,
    this.manufacturer,
    this.country,
    this.year,
    this.isRightHandDrive,
  });

  factory VinValidationResponse.fromJson(Map<String, dynamic> json) {
    return VinValidationResponse(
      vin: json['vin'] as String,
      isValid: json['is_valid'] as bool? ?? false,
      errors: (json['errors'] as List? ?? []).map((e) => e as String).toList(),
      checkDigitValid: json['check_digit_valid'] as bool?,
      manufacturer: json['manufacturer'] as String?,
      country: json['country'] as String?,
      year: json['year'] as int?,
      isRightHandDrive: json['is_right_hand_drive'] as bool?,
    );
  }
}

class ModificationItem {
  final String name;
  final String category;
  final String? brand;
  final String? notes;

  const ModificationItem({
    required this.name,
    required this.category,
    this.brand,
    this.notes,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'category': category,
        if (brand != null) 'brand': brand,
        if (notes != null) 'notes': notes,
      };

  factory ModificationItem.fromJson(Map<String, dynamic> json) {
    return ModificationItem(
      name: json['name'] as String,
      category: json['category'] as String,
      brand: json['brand'] as String?,
      notes: json['notes'] as String?,
    );
  }
}

class ModificationChecklistRequest {
  final List<ModificationItem> modifications;
  final String vehicleCategory;
  final VassJurisdiction jurisdiction;

  const ModificationChecklistRequest({
    required this.modifications,
    this.vehicleCategory = 'passenger',
    this.jurisdiction = VassJurisdiction.VIC,
  });

  Map<String, dynamic> toJson() => {
        'modifications': modifications.map((m) => m.toJson()).toList(),
        'vehicle_category': vehicleCategory,
        'jurisdiction': jurisdiction.value,
      };
}

class ChecklistItemOut {
  final String id;
  final String category;
  final String name;
  final String description;
  final bool required;
  final List<String> adrReferences;
  final List<String> vsbReferences;
  final int? estCostAud;
  final String? notes;

  const ChecklistItemOut({
    required this.id,
    required this.category,
    required this.name,
    required this.description,
    required this.required,
    this.adrReferences = const [],
    this.vsbReferences = const [],
    this.estCostAud,
    this.notes,
  });

  factory ChecklistItemOut.fromJson(Map<String, dynamic> json) {
    return ChecklistItemOut(
      id: json['id'] as String,
      category: json['category'] as String,
      name: json['name'] as String,
      description: json['description'] as String,
      required: json['required'] as bool? ?? true,
      adrReferences: (json['adr_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      vsbReferences: (json['vsb_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      estCostAud: json['est_cost_aud'] as int?,
      notes: json['notes'] as String?,
    );
  }
}

class ModificationChecklistResponse {
  final List<ModificationItem> modifications;
  final String vehicleCategory;
  final String jurisdiction;
  final List<ChecklistItemOut> checklist;
  final int totalItems;
  final int requiredItems;
  final int estTotalCostAud;

  const ModificationChecklistResponse({
    required this.modifications,
    required this.vehicleCategory,
    required this.jurisdiction,
    required this.checklist,
    required this.totalItems,
    required this.requiredItems,
    required this.estTotalCostAud,
  });

  factory ModificationChecklistResponse.fromJson(Map<String, dynamic> json) {
    return ModificationChecklistResponse(
      modifications: (json['modifications'] as List? ?? [])
          .map((e) => ModificationItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      vehicleCategory: json['vehicle_category'] as String? ?? 'passenger',
      jurisdiction: json['jurisdiction'] as String? ?? 'VIC',
      checklist: (json['checklist'] as List? ?? [])
          .map((e) => ChecklistItemOut.fromJson(e as Map<String, dynamic>))
          .toList(),
      totalItems: json['total_items'] as int? ?? 0,
      requiredItems: json['required_items'] as int? ?? 0,
      estTotalCostAud: json['est_total_cost_aud'] as int? ?? 0,
    );
  }
}

class ComplianceResultDetail {
  final String name;
  final String category;
  final String status;
  final List<String> adrReferences;
  final List<String> vsbReferences;
  final String? notes;
  final String? conditionalDetails;
  final String? createdAt;

  const ComplianceResultDetail({
    required this.name,
    required this.category,
    required this.status,
    this.adrReferences = const [],
    this.vsbReferences = const [],
    this.notes,
    this.conditionalDetails,
    this.createdAt,
  });

  factory ComplianceResultDetail.fromJson(Map<String, dynamic> json) {
    return ComplianceResultDetail(
      name: json['name'] as String,
      category: json['category'] as String,
      status: json['status'] as String? ?? '',
      adrReferences: (json['adr_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      vsbReferences: (json['vsb_references'] as List? ?? [])
          .map((e) => e as String)
          .toList(),
      notes: json['notes'] as String?,
      conditionalDetails: json['conditional_details'] as String?,
      createdAt: json['created_at'] as String?,
    );
  }
}

class ComplianceAggregationRequest {
  final String precheckId;

  const ComplianceAggregationRequest({required this.precheckId});

  Map<String, dynamic> toJson() => {'precheck_id': precheckId};
}

class ComplianceAggregationResponse {
  final double overallScore;
  final int totalMods;
  final int passed;
  final int failed;
  final int conditional;
  final int pending;
  final bool requiresEngineerReview;
  final String summary;
  final List<ComplianceResultDetail> results;

  const ComplianceAggregationResponse({
    required this.overallScore,
    required this.totalMods,
    required this.passed,
    required this.failed,
    required this.conditional,
    required this.pending,
    required this.requiresEngineerReview,
    required this.summary,
    this.results = const [],
  });

  factory ComplianceAggregationResponse.fromJson(Map<String, dynamic> json) {
    return ComplianceAggregationResponse(
      overallScore: (json['overall_score'] as num? ?? 0).toDouble(),
      totalMods: json['total_mods'] as int? ?? 0,
      passed: json['passed'] as int? ?? 0,
      failed: json['failed'] as int? ?? 0,
      conditional: json['conditional'] as int? ?? 0,
      pending: json['pending'] as int? ?? 0,
      requiresEngineerReview:
          (json['requires_engineer_review'] as bool?) ?? false,
      summary: json['summary'] as String? ?? '',
      results: (json['results'] as List? ?? [])
          .map((e) => ComplianceResultDetail.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ModificationCreate {
  final String name;
  final String category;
  final String? brand;
  final String? partNumber;
  final String? description;
  final String? vehicleId;
  final String? precheckId;

  const ModificationCreate({
    required this.name,
    required this.category,
    this.brand,
    this.partNumber,
    this.description,
    this.vehicleId,
    this.precheckId,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'category': category,
        if (brand != null) 'brand': brand,
        if (partNumber != null) 'part_number': partNumber,
        if (description != null) 'description': description,
        if (vehicleId != null) 'vehicle_id': vehicleId,
        if (precheckId != null) 'precheck_id': precheckId,
      };
}

class ModificationOut {
  final String id;
  final String name;
  final String category;
  final String? brand;
  final String? partNumber;
  final String? description;
  final String? vehicleId;
  final String? precheckId;
  final DateTime? createdAt;

  const ModificationOut({
    required this.id,
    required this.name,
    required this.category,
    this.brand,
    this.partNumber,
    this.description,
    this.vehicleId,
    this.precheckId,
    this.createdAt,
  });

  factory ModificationOut.fromJson(Map<String, dynamic> json) {
    return ModificationOut(
      id: json['id'] as String,
      name: json['name'] as String,
      category: json['category'] as String,
      brand: json['brand'] as String?,
      partNumber: json['part_number'] as String?,
      description: json['description'] as String?,
      vehicleId: json['vehicle_id'] as String?,
      precheckId: json['precheck_id'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'] as String)
          : null,
    );
  }
}