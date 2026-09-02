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

/// A cached petrol price feed row (AUT-1813), served to the price-map frontend.
class FuelPrice {
  final String state;
  final String stationCode;
  final String? stationName;
  final String? brand;
  final String? address;
  final double? latitude;
  final double? longitude;
  final String fuelType;
  final double? price;
  final String currency;
  final DateTime? updatedAt;
  final double? priceDeltaPct;

  const FuelPrice({
    required this.state,
    required this.stationCode,
    required this.fuelType,
    this.stationName,
    this.brand,
    this.address,
    this.latitude,
    this.longitude,
    this.price,
    this.currency = 'AUD',
    this.updatedAt,
    this.priceDeltaPct,
  });

  factory FuelPrice.fromJson(Map<String, dynamic> j) => FuelPrice(
        state: j['state'] as String,
        stationCode: j['station_code'] as String,
        fuelType: j['fuel_type'] as String,
        stationName: j['station_name'] as String?,
        brand: j['brand'] as String?,
        address: j['address'] as String?,
        latitude: (j['latitude'] as num?)?.toDouble(),
        longitude: (j['longitude'] as num?)?.toDouble(),
        price: (j['price'] as num?)?.toDouble(),
        currency: j['currency'] as String? ?? 'AUD',
        updatedAt: DateTime.tryParse((j['updated_at'] as String?) ?? ''),
        priceDeltaPct: (j['price_delta_pct'] as num?)?.toDouble(),
      );
}

/// A user's servo-spy favourite (station + fuel type) to watch for moves (AUT-1859).
class FuelPriceWatchlist {
  final String id;
  final String state;
  final String stationCode;
  final String? stationName;
  final String? brand;
  final String fuelType;
  final String direction;
  final double thresholdPct;
  final DateTime? createdAt;

  const FuelPriceWatchlist({
    required this.id,
    required this.state,
    required this.stationCode,
    required this.fuelType,
    this.stationName,
    this.brand,
    this.direction = 'both',
    this.thresholdPct = 5.0,
    this.createdAt,
  });

  factory FuelPriceWatchlist.fromJson(Map<String, dynamic> j) => FuelPriceWatchlist(
        id: j['id'] as String,
        state: j['state'] as String,
        stationCode: j['station_code'] as String,
        fuelType: j['fuel_type'] as String,
        stationName: j['station_name'] as String?,
        brand: j['brand'] as String?,
        direction: j['direction'] as String? ?? 'both',
        thresholdPct: (j['threshold_pct'] as num?)?.toDouble() ?? 5.0,
        createdAt: DateTime.tryParse((j['created_at'] as String?) ?? ''),
      );
}
