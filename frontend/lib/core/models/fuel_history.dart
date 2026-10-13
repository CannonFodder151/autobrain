part of models;

/// Backend `fuel_prices.price` is CENTS per litre (FuelPriceOut).
double priceCentsToDollars(double cents) => cents / 100;

/// Chart axis/tooltip label for a value already in dollars per litre.
String formatChartPrice(double dollars) => '\$${dollars.toStringAsFixed(2)}';

class FuelHistoryPoint {
  final String fuelType;
  final double price;
  final DateTime effectiveAt;

  const FuelHistoryPoint({
    required this.fuelType,
    required this.price,
    required this.effectiveAt,
  });

  factory FuelHistoryPoint.fromJson(Map<String, dynamic> j) => FuelHistoryPoint(
        fuelType: j['fuel_type'] as String? ?? '',
        price: (j['price'] as num).toDouble(),
        effectiveAt: DateTime.parse(j['effective_at'] as String).toLocal(),
      );
}

class FuelStationHistory {
  final String stationId;
  final String source;
  final String? fuelType;
  final int days;
  final List<FuelHistoryPoint> series;

  const FuelStationHistory({
    required this.stationId,
    required this.source,
    this.fuelType,
    required this.days,
    required this.series,
  });

  bool get isEmpty => series.isEmpty;

  factory FuelStationHistory.fromJson(Map<String, dynamic> j) =>
      FuelStationHistory(
        stationId: j['station_id'] as String? ?? '',
        source: j['source'] as String? ?? '',
        fuelType: j['fuel_type'] as String?,
        days: (j['days'] as num?)?.toInt() ?? 0,
        series: ((j['series'] as List?) ?? const [])
            .map((e) => FuelHistoryPoint.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}