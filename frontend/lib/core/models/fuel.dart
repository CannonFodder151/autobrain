part of models;

class FuelLog {
  final String id;
  final String fillDate;
  final int odometerKm;
  final double litres, pricePerLitre, totalCost;
  final bool isFullTank;
  final double? lPer100km, costPerKm;
  final String? notes, receiptId;

  const FuelLog({
    required this.id,
    required this.fillDate,
    required this.odometerKm,
    required this.litres,
    required this.pricePerLitre,
    required this.totalCost,
    this.isFullTank = true,
    this.lPer100km,
    this.costPerKm,
    this.notes,
    this.receiptId,
  });

  factory FuelLog.fromJson(Map<String, dynamic> j) => FuelLog(
        id: j['id'] as String,
        fillDate: j['fill_date'] as String,
        odometerKm: j['odometer_km'] as int,
        litres: (j['litres'] as num).toDouble(),
        pricePerLitre: (j['price_per_litre'] as num).toDouble(),
        totalCost: (j['total_cost'] as num).toDouble(),
        isFullTank: (j['is_full_tank'] as bool?) ?? true,
        lPer100km: (j['l_per_100km'] as num?)?.toDouble(),
        costPerKm: (j['cost_per_km'] as num?)?.toDouble(),
        notes: j['notes'] as String?,
        receiptId: j['receipt_id'] as String?,
      );
}
