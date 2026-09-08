part of models;

class Vehicle {
  final String id;
  final String nickname;
  final String? rego, regoState, vin, make, model, colour, bodyType, engine, transmission;
  final int? year, odometerKm;
  final String condition;
  final String vehicleType;
  final bool isPrimary, clubReg;
  final bool autoSuggestService;
  final String? fuelType;
  final bool isShared;
  final String? sharedBy;
  /// AUT-2415 — populated nightly by the AUT-2414 Celery beat job. Null until
  /// the backend has run a rego lookup for this vehicle.
  final String? regoStatus;
  /// ISO date string (YYYY-MM-DD) of rego expiry; null if unknown.
  final String? regoExpiryDate;

  const Vehicle({
    required this.id,
    required this.nickname,
    this.rego,
    this.regoState,
    this.vin,
    this.make,
    this.model,
    this.colour,
    this.bodyType,
    this.engine,
    this.transmission,
    this.year,
    this.odometerKm,
    this.condition = 'good',
    this.vehicleType = 'car',
    this.isPrimary = false,
    this.clubReg = false,
    this.autoSuggestService = false,
    this.fuelType,
    this.isShared = false,
    this.sharedBy,
    this.regoStatus,
    this.regoExpiryDate,
  });

  String get displayName => '$nickname'
      '${make != null ? ' ($make $model)' : ''}'.trim();

  /// Dropdown/list label: appends '(Invited by <Display Name>)' for vehicles
  /// the user accesses through a share rather than owning.
  String get dropdownLabel => isShared
      ? '$displayName (Invited by ${sharedBy ?? 'Unknown'})'
      : displayName;

  /// True when [regoStatus] and [regoExpiryDate] are both present. UI hides the
  /// rego badge / expiry line unless this returns true (forward-compatible with
  /// AUT-2414's nightly job: vehicles with no rego lookup yet simply show nothing).
  bool get hasRegoData =>
      regoStatus != null && regoStatus!.isNotEmpty &&
      regoExpiryDate != null && regoExpiryDate!.isNotEmpty;

  /// Human-readable expiry (e.g. "12 Mar 2027"). Returns null when unknown.
  String? get formattedRegoExpiry {
    final raw = regoExpiryDate;
    if (raw == null || raw.isEmpty) return null;
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return raw;
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    final m = months[parsed.month - 1];
    return '$parsed.day $m ${parsed.year}';
  }

  @override
  bool operator ==(Object other) => other is Vehicle && other.id == id;

  @override
  int get hashCode => id.hashCode;

  /// Re-resolves [current] against a freshly fetched [vehicles] list so the
  /// stored selection always refers to a live instance in the list, keeping
  /// the dropdown and card in sync across refreshes.
  static Vehicle? resolveSelection(List<Vehicle> vehicles, Vehicle? current) {
    if (current != null) {
      for (final v in vehicles) {
        if (v.id == current.id) return v;
      }
    }
    for (final v in vehicles) {
      if (v.isPrimary) return v;
    }
    return vehicles.isEmpty ? null : vehicles.first;
  }

  /// Resolves the live vehicle for [vehicleId] from [vehicles], falling back to
  /// the primary (then first) vehicle when [vehicleId] isn't in the list.
  static Vehicle? byId(List<Vehicle> vehicles, String vehicleId) {
    for (final v in vehicles) {
      if (v.id == vehicleId) return v;
    }
    return resolveSelection(vehicles, null);
  }

  factory Vehicle.fromJson(Map<String, dynamic> j) => Vehicle(
        id: j['id'] as String,
        nickname: j['nickname'] as String,
        rego: j['rego'] as String?,
        regoState: j['rego_state'] as String?,
        vin: j['vin'] as String?,
        make: j['make'] as String?,
        model: j['model'] as String?,
        colour: j['colour'] as String?,
        bodyType: j['body_type'] as String?,
        engine: j['engine'] as String?,
        transmission: j['transmission'] as String?,
        year: j['year'] as int?,
        odometerKm: j['odometer_km'] as int?,
        condition: (j['condition'] as String?) ?? 'good',
        vehicleType: (j['vehicle_type'] as String?) ?? 'car',
        isPrimary: (j['is_primary'] as bool?) ?? false,
        clubReg: (j['club_reg'] as bool?) ?? false,
        autoSuggestService: (j['auto_suggest_service'] as bool?) ?? false,
        fuelType: (j['fuel_type'] as String?),
        isShared: (j['is_shared'] as bool?) ?? false,
        sharedBy: j['shared_by'] as String?,
        regoStatus: j['rego_status'] as String?,
        regoExpiryDate: j['rego_expiry_date'] as String?,
      );
}
