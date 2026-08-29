import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/models.dart';

void main() {
  group('FuelPriceQuote', () {
    test('parses cents-per-litre + coords', () {
      final q = FuelPriceQuote.fromJson({
        'fuel_type': 'U91',
        'price_cpl': 189.9,
        'station': '11-Seven Swanston',
        'suburb': 'Melbourne',
        'state': 'VIC',
        'postcode': '3000',
        'lat': -37.8136,
        'lng': 144.9631,
        'rank': 1,
        'distance_km': 2.4,
      });
      expect(q.fuelType, 'U91');
      expect(q.priceCpl, 189.9);
      expect(q.station, '11-Seven Swanston');
      expect(q.lat, -37.8136);
      expect(q.rank, 1);
      expect(q.distanceKm, 2.4);
    });
  });

  group('FuelStationDetail', () {
    test('parses all fuel-type prices', () {
      final d = FuelStationDetail.fromJson({
        'station': '11-Seven Swanston',
        'suburb': 'Melbourne',
        'state': 'VIC',
        'postcode': '3000',
        'address': 'Melbourne VIC 3000',
        'lat': -37.8136,
        'lng': 144.9631,
        'prices': [
          {'fuel_type': 'U91', 'price_cpl': 189.9},
          {'fuel_type': 'E10', 'price_cpl': 165.3},
        ],
      });
      expect(d.station, '11-Seven Swanston');
      expect(d.prices.length, 2);
      expect(d.prices.first.fuelType, 'U91');
      expect(d.prices.first.priceCpl, 189.9);
      expect(d.prices.last.fuelType, 'E10');
    });

    test('tolerates missing prices', () {
      final d = FuelStationDetail.fromJson({
        'station': 'X',
        'suburb': '',
        'state': '',
        'postcode': '',
        'address': '',
        'prices': null,
      });
      expect(d.prices, isEmpty);
    });
  });
}
