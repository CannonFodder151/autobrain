/// Pure data + sort logic for the Servo Spy list view (AUT-1821).
///
/// Kept free of Flutter so it is unit-testable without the widget framework.
/// The screen renders [ServoStationRow]s and calls [sortStationRows] to apply
/// the chosen sort metric.

enum ServoSortMetric { price, distance }

class ServoStationRow {
  final String name;
  final String? brand;
  final String? logoUrl;
  final double? distanceKm;
  final double? priceCents;
  final String? fuelType;
  final List<ServoFuelPrice> prices;

  const ServoStationRow({
    required this.name,
    this.brand,
    this.logoUrl,
    this.distanceKm,
    this.priceCents,
    this.fuelType,
    this.prices = const [],
  });

  /// Price in cents for [fuelType] in [prices], or null if missing.
  /// Mirrors `_MapStation.priceFor` on the map view (AUT-2105).
  static double? priceForFrom(List<ServoFuelPrice> prices, String fuelType) {
    for (final p in prices) {
      if (p.fuelType == fuelType) return p.priceCents;
    }
    return null;
  }

  /// Price in cents for [fuelType] on this row, or null if the station
  /// doesn't list it.
  double? priceFor(String fuelType) => priceForFrom(prices, fuelType);
}

class ServoFuelPrice {
  final String fuelType;
  final double? priceCents;
  const ServoFuelPrice({required this.fuelType, this.priceCents});
}

/// Sorts [rows] in place by [metric], ascending, and returns it.
///
/// Price mode: cheapest first. Distance mode: nearest first. Rows missing the
/// sort metric sort to the end (treated as +inf).
List<ServoStationRow> sortStationRows(
  List<ServoStationRow> rows,
  ServoSortMetric metric,
) {
  if (metric == ServoSortMetric.price) {
    rows.sort((a, b) => (a.priceCents ?? double.infinity)
        .compareTo(b.priceCents ?? double.infinity));
  } else {
    rows.sort((a, b) => (a.distanceKm ?? double.infinity)
        .compareTo(b.distanceKm ?? double.infinity));
  }
  return rows;
}
