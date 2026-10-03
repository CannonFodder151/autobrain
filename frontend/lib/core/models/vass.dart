part of models;

/// Australian state/territory jurisdictions for VASS compliance.
enum VassJurisdiction {
  VIC, NSW, QLD, SA, WA, TAS, ACT, NT;

  String get displayName {
    switch (this) {
      case VassJurisdiction.VIC: return 'Victoria (VIC)';
      case VassJurisdiction.NSW: return 'New South Wales (NSW)';
      case VassJurisdiction.QLD: return 'Queensland (QLD)';
      case VassJurisdiction.SA: return 'South Australia (SA)';
      case VassJurisdiction.WA: return 'Western Australia (WA)';
      case VassJurisdiction.TAS: return 'Tasmania (TAS)';
      case VassJurisdiction.ACT: return 'Australian Capital Territory (ACT)';
      case VassJurisdiction.NT: return 'Northern Territory (NT)';
    }
  }

  static VassJurisdiction? fromString(String? v) {
    if (v == null) return null;
    for (final j in VassJurisdiction.values) {
      if (j.name == v) return j;
    }
    return null;
  }
}

/// Per-modification compliance outcome.
enum VassComplianceStatus {
  pass, fail, conditional, pending, na;

  String get displayName {
    switch (this) {
      case VassComplianceStatus.pass: return 'Pass';
      case VassComplianceStatus.fail: return 'Fail';
      case VassComplianceStatus.conditional: return 'Conditional';
      case VassComplianceStatus.pending: return 'Pending';
      case VassComplianceStatus.na: return 'N/A';
    }
  }

  static VassComplianceStatus fromString(String? v) {
    if (v == null) return VassComplianceStatus.pending;
    return VassComplianceStatus.values.firstWhere(
      (s) => s.name == v,
      orElse: () => VassComplianceStatus.pending,
    );
  }
}

/// Pre-check wizard session.
class VassPrecheck {
  final String id;
  final String vehicleId;
  final String userId;
  final VassJurisdiction jurisdiction;
  final VassPrecheckStatus status;
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

  const VassPrecheck({
    required this.id,
    required this.vehicleId,
    required this.userId,
    this.jurisdiction = VassJurisdiction.VIC,
    this.status = VassPrecheckStatus.draft,
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

  factory VassPrecheck.fromJson(Map<String, dynamic> j) {
    final modsJson = j['modifications_json'];
    List<ModificationSelection> mods = [];
    if (modsJson is Map && modsJson['mods'] is List) {
      mods = (modsJson['mods'] as List)
          .map((m) => ModificationSelection.fromJson(m as Map<String, dynamic>))
          .toList();
    } else if (j['modifications'] is List) {
      mods = (j['modifications'] as List)
          .map((m) => ModificationSelection.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    return VassPrecheck(
      id: j['id'] as String,
      vehicleId: j['vehicle_id'] as String,
      userId: j['user_id'] as String,
      jurisdiction: VassJurisdiction.fromString(j['jurisdiction'] as String?) ?? VassJurisdiction.VIC,
      status: VassPrecheckStatus.fromString(j['status'] as String?),
      vin: j['vin'] as String?,
      make: j['make'] as String?,
      model: j['model'] as String?,
      year: j['year'] as int?,
      bodyType: j['body_type'] as String?,
      engine: j['engine'] as String?,
      transmission: j['transmission'] as String?,
      modifications: mods,
      completedAt: j['completed_at'] != null ? DateTime.tryParse(j['completed_at'] as String) : null,
      createdAt: DateTime.parse(j['created_at'] as String),
      updatedAt: DateTime.parse(j['updated_at'] as String),
    );
  }

  /// Overall compliance score (0-100) from results.
  double? computeScore(List<VassComplianceResult> results) {
    if (results.isEmpty) return null;
    final passed = results.where((r) => r.status == VassComplianceStatus.pass).length;
    return passed / results.length * 100;
  }
}

enum VassPrecheckStatus {
  draft, inProgress, completed, archived;

  String get displayName {
    switch (this) {
      case VassPrecheckStatus.draft: return 'Draft';
      case VassPrecheckStatus.inProgress: return 'In Progress';
      case VassPrecheckStatus.completed: return 'Completed';
      case VassPrecheckStatus.archived: return 'Archived';
    }
  }

  static VassPrecheckStatus fromString(String? v) {
    if (v == null) return VassPrecheckStatus.draft;
    if (v == 'in_progress') return VassPrecheckStatus.inProgress;
    return VassPrecheckStatus.values.firstWhere(
      (s) => s.name == v,
      orElse: () => VassPrecheckStatus.draft,
    );
  }
}

/// Modification selection in pre-check wizard.
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

  factory ModificationSelection.fromJson(Map<String, dynamic> j) =>
      ModificationSelection(
        name: j['name'] as String,
        category: j['category'] as String,
        brand: j['brand'] as String?,
        notes: j['notes'] as String?,
      );

  Map<String, dynamic> toJson() => {
    'name': name,
    'category': category,
    if (brand != null) 'brand': brand,
    if (notes != null) 'notes': notes,
  };
}

/// Individual modification compliance result.
class VassComplianceResult {
  final String id;
  final String precheckId;
  final String modificationName;
  final String category;
  final VassComplianceStatus status;
  final List<String> adrReferences;
  final List<String> vsbReferences;
  final List<String> vsb6References;
  final String? notes;
  final String? conditionalDetails;
  final DateTime createdAt;

  const VassComplianceResult({
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

  factory VassComplianceResult.fromJson(Map<String, dynamic> j) =>
      VassComplianceResult(
        id: j['id'] as String,
        precheckId: j['precheck_id'] as String,
        modificationName: j['modification_name'] as String,
        category: j['category'] as String,
        status: VassComplianceStatus.fromString(j['status'] as String?),
        adrReferences: _toStringList(j['adr_references']),
        vsbReferences: _toStringList(j['vsb_references']),
        vsb6References: _toStringList(j['vsb6_references']),
        notes: j['notes'] as String?,
        conditionalDetails: j['conditional_details'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
      );
}

List<String> _toStringList(dynamic v) {
  if (v is List) return v.map((e) => e.toString()).toList();
  if (v is String) {
    try {
      final parsed = jsonDecode(v);
      if (parsed is List) return parsed.map((e) => e.toString()).toList();
    } catch (_) {}
  }
  return [];
}

/// VASS engineer.
class VassEngineer {
  final String id;
  final VassJurisdiction jurisdiction;
  final String engineerType;
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

  const VassEngineer({
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
    this.isActive = true,
    this.rating,
    this.reviewCount = 0,
    required this.createdAt,
    required this.updatedAt,
  });

  factory VassEngineer.fromJson(Map<String, dynamic> j) => VassEngineer(
    id: j['id'] as String,
    jurisdiction: VassJurisdiction.fromString(j['jurisdiction'] as String?) ?? VassJurisdiction.VIC,
    engineerType: j['engineer_type'] as String,
    name: j['name'] as String,
    businessName: j['business_name'] as String?,
    abn: j['abn'] as String?,
    email: j['email'] as String?,
    phone: j['phone'] as String?,
    address: j['address'] as String?,
    suburb: j['suburb'] as String?,
    postcode: j['postcode'] as String?,
    specialisations: _toStringList(j['specialisations']),
    licenseNumber: j['license_number'] as String?,
    licenseExpiry: j['license_expiry'] != null ? DateTime.tryParse(j['license_expiry'] as String) : null,
    isActive: (j['is_active'] as bool?) ?? true,
    rating: (j['rating'] as num?)?.toDouble(),
    reviewCount: (j['review_count'] as int?) ?? 0,
    createdAt: DateTime.parse(j['created_at'] as String),
    updatedAt: DateTime.parse(j['updated_at'] as String),
  );
}

/// Import pathway result.
class ImportPathway {
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

  const ImportPathway({
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
  });

  factory ImportPathway.fromJson(Map<String, dynamic> j) {
    Map<String, dynamic>? reqs;
    if (j['requirements'] is Map) {
      reqs = j['requirements'] as Map<String, dynamic>;
    } else if (j['requirements_json'] is String) {
      try {
        final parsed = jsonDecode(j['requirements_json'] as String);
        if (parsed is Map) reqs = Map<String, dynamic>.from(parsed);
      } catch (_) {}
    }
    return ImportPathway(
      id: j['id'] as String,
      vin: j['vin'] as String,
      jurisdiction: VassJurisdiction.fromString(j['jurisdiction'] as String?) ?? VassJurisdiction.VIC,
      vehicleMake: j['vehicle_make'] as String?,
      vehicleModel: j['vehicle_model'] as String?,
      vehicleYear: j['vehicle_year'] as int?,
      pathwayType: j['pathway_type'] as String,
      eligibility: j['eligibility'] as String,
      requirements: reqs,
      adrRequirements: _toStringList(j['adr_requirements']),
      createdAt: DateTime.parse(j['created_at'] as String),
    );
  }

  String get pathwayDisplayName {
    switch (pathwayType) {
      case 'sevs': return 'Specialist & Enthusiast Vehicle Scheme (SEVS)';
      case 'raws': return 'Register of Approved Vehicles (RAV)';
      case 'personal_import': return 'Personal Import';
      case 'assessment_required': return 'Assessment Required';
      default: return pathwayType;
    }
  }

  bool get isEligible => eligibility == 'eligible';
  bool get isConditional => eligibility == 'conditional';
}

/// Document checklist item for import pathway.
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

  factory DocumentChecklistItem.fromJson(Map<String, dynamic> j) =>
      DocumentChecklistItem(
        name: j['name'] as String,
        description: j['description'] as String?,
        required: (j['required'] as bool?) ?? true,
        provided: (j['provided'] as bool?) ?? false,
        notes: j['notes'] as String?,
      );
}

/// Compliance pack (PDF).
class CompliancePack {
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

  const CompliancePack({
    required this.id,
    required this.precheckId,
    required this.filename,
    required this.fileSize,
    this.overallScore,
    this.totalMods = 0,
    this.passedMods = 0,
    this.failedMods = 0,
    this.conditionalMods = 0,
    required this.createdAt,
  });

  factory CompliancePack.fromJson(Map<String, dynamic> j) => CompliancePack(
    id: j['id'] as String,
    precheckId: j['precheck_id'] as String,
    filename: j['filename'] as String,
    fileSize: (j['file_size'] as int?) ?? 0,
    overallScore: (j['overall_score'] as num?)?.toDouble(),
    totalMods: (j['total_mods'] as int?) ?? 0,
    passedMods: (j['passed_mods'] as int?) ?? 0,
    failedMods: (j['failed_mods'] as int?) ?? 0,
    conditionalMods: (j['conditional_mods'] as int?) ?? 0,
    createdAt: DateTime.parse(j['created_at'] as String),
  );
}