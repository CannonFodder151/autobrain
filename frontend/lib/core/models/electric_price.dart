part of models;

/// A cached EV charging station price row (AUT-412 + AUT-466).
class ChargingStationPrice {
  final String stationId;
  final String? stationName;
  final String? brand;
  final String? address;
  final double? latitude;
  final double? longitude;
  final String connectorType;
  final double? pricePerKwh;
  final String currency;
  final DateTime? updatedAt;

  const ChargingStationPrice({
    required this.stationId,
    required this.connectorType,
    this.stationName,
    this.brand,
    this.address,
    this.latitude,
    this.longitude,
    this.pricePerKwh,
    this.currency = 'AUD',
    this.updatedAt,
  });

  factory ChargingStationPrice.fromJson(Map<String, dynamic> j) =>
      ChargingStationPrice(
        stationId: j['station_id'] as String,
        stationName: j['station_name'] as String?,
        brand: j['brand'] as String?,
        address: j['address'] as String?,
        latitude: (j['latitude'] as num?)?.toDouble(),
        longitude: (j['longitude'] as num?)?.toDouble(),
        connectorType: j['connector_type'] as String,
        pricePerKwh: (j['price_per_kwh'] as num?)?.toDouble(),
        currency: j['currency'] as String? ?? 'AUD',
        updatedAt: DateTime.tryParse((j['updated_at'] as String?) ?? ''),
      );
}

/// A user's Electric Spy watchlist entry (station + connector type) (AUT-466).
class ChargingStationPriceWatchlist {
  final String id;
  final String stationId;
  final String? stationName;
  final String? brand;
  final String connectorType;
  final String direction;
  final double thresholdPct;
  final DateTime? createdAt;

  const ChargingStationPriceWatchlist({
    required this.id,
    required this.stationId,
    required this.connectorType,
    this.stationName,
    this.brand,
    this.direction = 'both',
    this.thresholdPct = 5.0,
    this.createdAt,
  });

  factory ChargingStationPriceWatchlist.fromJson(Map<String, dynamic> j) =>
      ChargingStationPriceWatchlist(
        id: j['id'] as String,
        stationId: j['station_id'] as String,
        stationName: j['station_name'] as String?,
        brand: j['brand'] as String?,
        connectorType: j['connector_type'] as String,
        direction: j['direction'] as String? ?? 'both',
        thresholdPct: (j['threshold_pct'] as num?)?.toDouble() ?? 5.0,
        createdAt: DateTime.tryParse((j['created_at'] as String?) ?? ''),
      );
}