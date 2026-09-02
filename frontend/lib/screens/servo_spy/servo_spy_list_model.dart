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

/// Picks the price entry for [fuelType] out of a raw API `prices` payload,
/// falling back to the first entry when no match exists.
///
/// The list view (AUT-1821) used to always take `prices[0]`, which could be a
/// different fuel than the one the user selected (AUT-2070). Centralising the
/// rule here keeps the parser deterministic and unit-testable.
({double? priceCents, String? fuelType}) pickPriceForFuel(
  List<dynamic> prices,
  String? fuelType,
) {
  if (prices.isEmpty) return (priceCents: null, fuelType: null);
  double? _toDouble(Object? v) {
    if (v is num) return v.toDouble();
    if (v is String) return double.tryParse(v);
    return null;
  }

  String? _toFuelType(Object? v) => v is String ? v : null;

  for (final p in prices) {
    if (p is! Map) continue;
    final ft = _toFuelType(p['fuel_type']);
    if (fuelType != null && ft == fuelType) {
      return (priceCents: _toDouble(p['price']), fuelType: ft);
    }
  }
  for (final p in prices) {
    if (p is! Map) continue;
    final ft = _toFuelType(p['fuel_type']);
    final price = _toDouble(p['price']);
    if (ft != null || price != null) {
      return (priceCents: price, fuelType: ft);
    }
  }
  return (priceCents: null, fuelType: null);
}

/// Parses one raw API station map into a [ServoStationRow], picking the price
/// for [selectedFuelType] when available.
ServoStationRow stationRowFromApi(
  Map<String, dynamic> m, {
  String? selectedFuelType,
}) {
  final prices = (m['prices'] as List?) ?? const [];
  final picked = pickPriceForFuel(prices, selectedFuelType);
  return ServoStationRow(
    name: m['name'] as String? ?? 'Unknown',
    brand: m['brand'] as String?,
    logoUrl: m['logo'] as String?,
    distanceKm: (m['distance_km'] as num?)?.toDouble(),
    priceCents: picked.priceCents,
    fuelType: picked.fuelType,
  );
}
