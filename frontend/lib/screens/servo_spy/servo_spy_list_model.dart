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

  const ServoStationRow({
    required this.name,
    this.brand,
    this.logoUrl,
    this.distanceKm,
    this.priceCents,
    this.fuelType,
  });
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
