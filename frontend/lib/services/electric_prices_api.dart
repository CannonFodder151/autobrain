/// Electric charging station price read API (AUT-412 + AUT-466).
///
/// Thin wrapper over [ApiClient]. Screens never touch the wire format. All
/// routes are authenticated and premium-gated; free accounts get 403.
library;

import '../core/api_client.dart';
import '../core/models.dart';

class ElectricPricesApi {
  ElectricPricesApi(this._api);
  final ApiClient _api;

  /// Latest cached EV charging station prices.
  Future<List<ChargingStationPrice>> listPrices({int limit = 200}) async {
    final data = await _api.get('/electric-prices/stations', query: {'limit': '$limit'})
        as List;
    return data
        .map((e) => ChargingStationPrice.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// The current user's Electric Spy watchlist.
  Future<List<ChargingStationPriceWatchlist>> listWatchlist() async {
    final data = await _api.get('/electric-prices/watchlist') as List;
    return data
        .map((e) => ChargingStationPriceWatchlist.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Add (or update) a favourite. Idempotent on (station_id, connector_type).
  Future<ChargingStationPriceWatchlist> addWatch({
    required String stationId,
    required String connectorType,
    String? stationName,
    String? brand,
    String direction = 'both',
    double thresholdPct = 5.0,
  }) async {
    final data = await _api.post('/electric-prices/watchlist', {
      'station_id': stationId,
      'connector_type': connectorType,
      if (stationName != null) 'station_name': stationName,
      if (brand != null) 'brand': brand,
      'direction': direction,
      'threshold_pct': thresholdPct,
    }) as Map<String, dynamic>;
    return ChargingStationPriceWatchlist.fromJson(data);
  }

  /// Remove a favourite by id.
  Future<void> removeWatch(String id) async {
    await _api.delete('/electric-prices/watchlist/$id');
  }
}