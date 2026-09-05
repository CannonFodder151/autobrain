/// Petrol price map read API (AUT-1813) + servo-spy favourites (AUT-1859).
///
/// Thin wrapper over [ApiClient]. Screens never touch the wire format. All
/// routes are authenticated and user-scoped; POST to the watch list is
/// idempotent on (state, station_code, fuel_type).
library;

import '../core/api_client.dart';
import '../core/models.dart';

class FuelPricesApi {
  FuelPricesApi(this._api);
  final ApiClient _api;

  /// Latest cached petrol prices for a state (the map marker set).
  Future<List<FuelPrice>> listPrices({String state = 'NSW'}) async {
    final data = await _api.get('/fuel-prices', query: {'state': state})
        as List;
    return data
        .map((e) => FuelPrice.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// The current user's servo-spy favourites.
  Future<List<FuelPriceWatchlist>> listWatchlist() async {
    final data = await _api.get('/fuel-prices/watchlist') as List;
    return data
        .map((e) => FuelPriceWatchlist.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Add (or update) a favourite. Idempotent on (state, station_code, fuel_type):
  /// re-adding just refreshes direction/threshold on the existing row.
  Future<FuelPriceWatchlist> addWatch({
    required String state,
    required String stationCode,
    required String fuelType,
    String direction = 'both',
    double thresholdPct = 5.0,
  }) async {
    final data = await _api.post('/fuel-prices/watchlist', {
      'state': state,
      'station_code': stationCode,
      'fuel_type': fuelType,
      'direction': direction,
      'threshold_pct': thresholdPct,
    }) as Map<String, dynamic>;
    return FuelPriceWatchlist.fromJson(data);
  }

  /// Remove a favourite by id.
  Future<void> removeWatch(String id) async {
    await _api.delete('/fuel-prices/watchlist/$id');
  }

  /// Last 30 days of fuel prices at a station (AUT-2375 endpoint, AUT-2376 chart).
  /// Backend returns a flat list: `{ "station_id": ..., "series": [
  ///   { "fuel_type": "E10", "price": 198.5, "effective_at": "2026-08-04T..." }, ... ] }`.
  /// We group by `fuel_type` so the chart screen can iterate one series per fuel.
  Future<StationPriceHistory> stationHistory(String stationId) async {
    final data = await _api.get('/fuel/stations/$stationId/history')
        as Map<String, dynamic>;
    return StationPriceHistory.fromJson(data);
  }
}

class StationPriceHistoryPoint {
  final DateTime date;
  final double priceCents; // cents per litre

  const StationPriceHistoryPoint({required this.date, required this.priceCents});

  factory StationPriceHistoryPoint.fromJson(Map<String, dynamic> m) {
    return StationPriceHistoryPoint(
      date: DateTime.parse(m['effective_at'] as String),
      priceCents: (m['price'] as num).toDouble(),
    );
  }
}

class StationPriceHistorySeries {
  final String fuelType;
  final List<StationPriceHistoryPoint> points;

  const StationPriceHistorySeries({
    required this.fuelType,
    required this.points,
  });
}

class StationPriceHistory {
  final String stationId;
  final List<StationPriceHistorySeries> series;

  const StationPriceHistory({
    required this.stationId,
    required this.series,
  });

  factory StationPriceHistory.fromJson(Map<String, dynamic> m) {
    final stationId = m['station_id'] as String? ?? '';
    // Flat response: each item is one (fuel, price, time) point. Group by fuel.
    final raw = (m['series'] as List?) ?? const [];
    final byFuel = <String, List<StationPriceHistoryPoint>>{};
    for (final item in raw) {
      final map = item as Map<String, dynamic>;
      final fuelType = map['fuel_type'] as String? ?? '';
      final p = StationPriceHistoryPoint.fromJson(map);
      (byFuel[fuelType] ??= <StationPriceHistoryPoint>[]).add(p);
    }
    final series = byFuel.entries
        .map((e) => StationPriceHistorySeries(fuelType: e.key, points: e.value))
        .toList()
      ..sort((a, b) => a.fuelType.compareTo(b.fuelType));
    return StationPriceHistory(stationId: stationId, series: series);
  }

  bool get isEmpty => series.every((s) => s.points.isEmpty);
}
