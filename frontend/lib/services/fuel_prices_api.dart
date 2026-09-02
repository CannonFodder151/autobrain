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
}
