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

/// One 7-Eleven price quote (cents per litre) from the Servo Spy map.
class FuelPriceQuote {
  final String fuelType;
  final double priceCpl;
  final String station;
  final String suburb;
  final String state;
  final String postcode;
  final double? lat;
  final double? lng;
  final int? rank;
  final double? distanceKm;

  const FuelPriceQuote({
    required this.fuelType,
    required this.priceCpl,
    required this.station,
    required this.suburb,
    required this.state,
    required this.postcode,
    this.lat,
    this.lng,
    this.rank,
    this.distanceKm,
  });

  factory FuelPriceQuote.fromJson(Map<String, dynamic> j) => FuelPriceQuote(
        fuelType: j['fuel_type'] as String,
        priceCpl: (j['price_cpl'] as num).toDouble(),
        station: j['station'] as String,
        suburb: j['suburb'] as String? ?? '',
        state: j['state'] as String? ?? '',
        postcode: j['postcode'] as String? ?? '',
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
        rank: j['rank'] as int?,
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
      );
}

/// One fuel type's price at a station detail (map bottom sheet).
class StationFuelPrice {
  final String fuelType;
  final double? priceCpl;

  const StationFuelPrice({required this.fuelType, this.priceCpl});

  factory StationFuelPrice.fromJson(Map<String, dynamic> j) => StationFuelPrice(
        fuelType: j['fuel_type'] as String,
        priceCpl: (j['price_cpl'] as num?)?.toDouble(),
      );
}

/// All fuel-type prices at a single 7-Eleven station (Servo Spy detail sheet).
class FuelStationDetail {
  final String station;
  final String suburb;
  final String state;
  final String postcode;
  final String address;
  final double? lat;
  final double? lng;
  final List<StationFuelPrice> prices;

  const FuelStationDetail({
    required this.station,
    required this.suburb,
    required this.state,
    required this.postcode,
    required this.address,
    this.lat,
    this.lng,
    required this.prices,
  });

  factory FuelStationDetail.fromJson(Map<String, dynamic> j) => FuelStationDetail(
        station: j['station'] as String,
        suburb: j['suburb'] as String? ?? '',
        state: j['state'] as String? ?? '',
        postcode: j['postcode'] as String? ?? '',
        address: j['address'] as String? ?? '',
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
        prices: (j['prices'] as List? ?? [])
            .map((e) => StationFuelPrice.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
