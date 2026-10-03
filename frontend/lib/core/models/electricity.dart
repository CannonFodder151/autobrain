part of models;

class ElectricityLog {
  final String id;
  final String chargeDate;
  final int odometerKm;
  final double kwh, pricePerKwh, totalCost;
  final bool isFullCharge;
  final double? kmPerKwh, costPerKm;
  final String? notes, receiptId;

  const ElectricityLog({
    required this.id,
    required this.chargeDate,
    required this.odometerKm,
    required this.kwh,
    required this.pricePerKwh,
    required this.totalCost,
    this.isFullCharge = true,
    this.kmPerKwh,
    this.costPerKm,
    this.notes,
    this.receiptId,
  });

  factory ElectricityLog.fromJson(Map<String, dynamic> j) => ElectricityLog(
        id: j['id'] as String,
        chargeDate: j['charge_date'] as String,
        odometerKm: j['odometer_km'] as int,
        kwh: (j['kwh'] as num).toDouble(),
        pricePerKwh: (j['price_per_kwh'] as num).toDouble(),
        totalCost: (j['total_cost'] as num).toDouble(),
        isFullCharge: (j['is_full_charge'] as bool?) ?? true,
        kmPerKwh: (j['km_per_kwh'] as num?)?.toDouble(),
        costPerKm: (j['cost_per_km'] as num?)?.toDouble(),
        notes: j['notes'] as String?,
        receiptId: j['receipt_id'] as String?,
      );
}
