part of models;

class Vehicle {
  final String id;
  final String nickname;
  final String? rego, vin, make, model, colour, bodyType, engine, transmission;
  final int? year, odometerKm;
  final String condition;
  final String vehicleType;
  final bool isPrimary, clubReg;

  const Vehicle({
    required this.id,
    required this.nickname,
    this.rego,
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
  });

  String get displayName => '$nickname'
      '${make != null ? ' ($make $model)' : ''}'.trim();

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

  factory Vehicle.fromJson(Map<String, dynamic> j) => Vehicle(
        id: j['id'] as String,
        nickname: j['nickname'] as String,
        rego: j['rego'] as String?,
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
      );
}
