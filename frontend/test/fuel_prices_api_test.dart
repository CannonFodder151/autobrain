import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/api_client.dart';
import 'package:autobrain/core/models.dart';
import 'package:autobrain/services/fuel_prices_api.dart';

/// Minimal [ApiClient] double that records calls and returns canned JSON.
class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  final calls = <String>[];
  Object? getResponse;
  Object? lastBody;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) {
    calls.add('GET $path${query != null ? '?${query.entries.map((e) => '${e.key}=${e.value}').join('&')}' : ''}');
    return Future.value(getResponse);
  }

  @override
  Future<dynamic> post(String path, [Object? body, Map<String, String>? headers]) {
    calls.add('POST $path');
    lastBody = body;
    return Future.value(getResponse);
  }

  @override
  Future<dynamic> delete(String path) {
    calls.add('DELETE $path');
    return Future.value(null);
  }
}

const _priceJson = {
  'state': 'NSW',
  'station_code': 'STN1',
  'station_name': 'Servo North',
  'brand': 'PetroCo',
  'address': '1 Main St',
  'latitude': -33.0,
  'longitude': 151.0,
  'fuel_type': 'E10',
  'price': 179.9,
  'currency': 'AUD',
  'updated_at': '2026-08-29T00:00:00.000Z',
  'price_delta_pct': 2.5,
};

const _watchJson = {
  'id': 'w1',
  'state': 'NSW',
  'station_code': 'STN1',
  'station_name': 'Servo North',
  'brand': 'PetroCo',
  'fuel_type': 'E10',
  'direction': 'both',
  'threshold_pct': 5.0,
  'created_at': '2026-08-29T00:00:00.000Z',
};

void main() {
  test('listPrices hits /fuel-prices?state=NSW and parses rows', () async {
    final api = _FakeApi()..getResponse = [_priceJson];
    final svc = FuelPricesApi(api);
    final prices = await svc.listPrices();
    expect(api.calls, ['GET /fuel-prices?state=NSW']);
    expect(prices, hasLength(1));
    expect(prices.first.stationCode, 'STN1');
    expect(prices.first.price, 179.9);
    expect(prices.first.priceDeltaPct, 2.5);
  });

  test('listWatchlist hits /fuel-prices/watchlist and parses rows', () async {
    final api = _FakeApi()..getResponse = [_watchJson];
    final svc = FuelPricesApi(api);
    final wl = await svc.listWatchlist();
    expect(api.calls, ['GET /fuel-prices/watchlist']);
    expect(wl.single.id, 'w1');
    expect(wl.single.direction, 'both');
    expect(wl.single.thresholdPct, 5.0);
  });

  test('addWatch POSTs the combo payload and returns the entry', () async {
    final api = _FakeApi()..getResponse = _watchJson;
    final svc = FuelPricesApi(api);
    final created = await svc.addWatch(
      state: 'NSW',
      stationCode: 'STN1',
      fuelType: 'E10',
    );
    expect(api.calls, ['POST /fuel-prices/watchlist']);
    expect(
      api.lastBody,
      {
        'state': 'NSW',
        'station_code': 'STN1',
        'fuel_type': 'E10',
        'direction': 'both',
        'threshold_pct': 5.0,
      },
    );
    expect(created.id, 'w1');
  });

  test('removeWatch DELETEs /fuel-prices/watchlist/{id}', () async {
    final api = _FakeApi();
    final svc = FuelPricesApi(api);
    await svc.removeWatch('w1');
    expect(api.calls, ['DELETE /fuel-prices/watchlist/w1']);
  });

  test('FuelPrice + FuelPriceWatchlist fromJson handle nulls', () {
    final p = FuelPrice.fromJson({
      'state': 'NSW',
      'station_code': 'STN2',
      'fuel_type': 'P98',
    });
    expect(p.price, isNull);
    expect(p.latitude, isNull);
    expect(p.priceDeltaPct, isNull);
    expect(p.currency, 'AUD');

    final w = FuelPriceWatchlist.fromJson({
      'id': 'w2',
      'state': 'NSW',
      'station_code': 'STN2',
      'fuel_type': 'P98',
    });
    expect(w.direction, 'both');
    expect(w.thresholdPct, 5.0);
  });
}
