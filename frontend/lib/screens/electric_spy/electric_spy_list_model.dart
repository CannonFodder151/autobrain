/// Electric Spy — pure data + sort logic (AUT-2435).
///
/// Mirror of `servo_spy_list_model.dart`. kWh replaces cents/L; connector
/// type replaces fuel type. Kept free of Flutter so it's unit-testable
/// without the widget framework.

enum EvSortMetric { price, distance, power }

class EvStationRow {
  final String name;
  final String? network;
  final double? distanceKm;
  final double? costPerKwh;
  final double? maxPowerKw;
  final String? connectorType;
  final String? status;
  final List<EvConnector> connectors;

  const EvStationRow({
    required this.name,
    this.network,
    this.distanceKm,
    this.costPerKwh,
    this.maxPowerKw,
    this.connectorType,
    this.status,
    this.connectors = const [],
  });
}

class EvConnector {
  final String connectorType;
  final double? maxPowerKw;
  final double? costPerKwh;
  final String? status;
  const EvConnector({
    required this.connectorType,
    this.maxPowerKw,
    this.costPerKwh,
    this.status,
  });
}

double? cheapestCostPerKwh(List<double?> costs) {
  final cleaned = costs.whereType<double>().where((c) => c > 0).toList();
  if (cleaned.isEmpty) return null;
  return cleaned.reduce((a, b) => a < b ? a : b);
}

double? maxPowerForRow(List<EvConnector> connectors) {
  final powers = connectors
      .map((c) => c.maxPowerKw)
      .whereType<double>()
      .where((p) => p > 0)
      .toList();
  if (powers.isEmpty) return null;
  return powers.reduce((a, b) => a > b ? a : b);
}

String? connectorForRow(List<EvConnector> connectors, String? preferred) {
  if (preferred != null) {
    for (final c in connectors) {
      if (c.connectorType == preferred) return c.connectorType;
    }
  }
  if (connectors.isEmpty) return null;
  return connectors.first.connectorType;
}

/// Sort [rows] in place by [metric] ascending. Rows missing the metric sort to
/// the end (+inf). Distance + price use the same logic as Servo Spy; power is
/// EV-specific (highest kW first when sorted by power).
List<EvStationRow> sortEvRows(
  List<EvStationRow> rows,
  EvSortMetric metric,
) {
  int _cmp(double? a, double? b, {bool descending = false}) {
    final aa = a ?? double.infinity;
    final bb = b ?? double.infinity;
    if (descending) return bb.compareTo(aa);
    return aa.compareTo(bb);
  }

  switch (metric) {
    case EvSortMetric.price:
      rows.sort((a, b) => _cmp(a.costPerKwh, b.costPerKwh));
    case EvSortMetric.distance:
      rows.sort((a, b) => _cmp(a.distanceKm, b.distanceKm));
    case EvSortMetric.power:
      rows.sort((a, b) => _cmp(a.maxPowerKw, b.maxPowerKw, descending: true));
  }
  return rows;
}

/// Parse one raw /api/ev/stations API map into an [EvStationRow].
///
/// Mirrors `stationRowFromApi` for fuel. [selectedConnectorType] picks a
/// connector when the station lists several; when the station does not match
/// the filter we still return the row with `connectors` populated so the list
/// can show what is available.
EvStationRow evStationRowFromApi(
  Map<String, dynamic> m, {
  String? selectedConnectorType,
}) {
  final rawConnectors = (m['connectors'] as List?) ?? const [];
  final connectors = rawConnectors
      .whereType<Map>()
      .map((c) => EvConnector(
        connectorType: (c['connector_type'] as String?) ?? '',
        maxPowerKw: (c['max_power_kw'] as num?)?.toDouble(),
        costPerKwh: (c['cost_per_kwh'] as num?)?.toDouble(),
        status: c['status'] as String?,
      ))
    .where((c) => c.connectorType.isNotEmpty)
    .toList();

  EvConnector? picked;
  if (selectedConnectorType != null) {
    for (final c in connectors) {
      if (c.connectorType == selectedConnectorType) {
        picked = c;
        break;
      }
    }
  }
  picked ??= connectors.isNotEmpty ? connectors.first : null;

  return EvStationRow(
    name: (m['name'] as String?) ?? 'Charging Station',
    network: m['network'] as String?,
    distanceKm: (m['distance_km'] as num?)?.toDouble(),
    costPerKwh: picked?.costPerKwh,
    maxPowerKw: picked?.maxPowerKw,
    connectorType: picked?.connectorType,
    status: picked?.status,
    connectors: connectors,
  );
}