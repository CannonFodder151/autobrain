import 'package:latlong2/latlong.dart';

class FuelPriceEntry {
  final String fuelType;
  final double? priceCents;
  final double? costPerKm;
  final double? avgFillCost;

  const FuelPriceEntry({
    required this.fuelType,
    this.priceCents,
    this.costPerKm,
    this.avgFillCost,
  });

  factory FuelPriceEntry.fromApi(Map<String, dynamic> p) {
    return FuelPriceEntry(
      fuelType: p['fuel_type'] as String? ?? '',
      priceCents: p['price'] != null ? (p['price'] as num).toDouble() : null,
      costPerKm: (p['cost_per_km'] as num?)?.toDouble(),
      avgFillCost: (p['avg_fill_cost'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'fuel_type': fuelType,
        'price': priceCents,
        'cost_per_km': costPerKm,
        'avg_fill_cost': avgFillCost,
      };
}

class MapStation {
  final String id;
  final String? brand;
  final String? name;
  final String? address;
  final String? logoUrl;
  final double? lat;
  final double? lon;
  final double? distanceKm;
  final List<FuelPriceEntry> prices;

  const MapStation({
    required this.id,
    this.brand,
    this.name,
    this.address,
    this.logoUrl,
    this.lat,
    this.lon,
    this.distanceKm,
    required this.prices,
  });

  factory MapStation.fromApi(Map<String, dynamic> m) {
    final rawPrices = (m['prices'] as List? ?? []) as List;
    return MapStation(
      id: m['id'] as String? ?? '',
      brand: m['brand'] as String?,
      name: m['name'] as String? ?? 'Unknown',
      address: m['address'] as String?,
      logoUrl: m['logo'] as String?,
      lat: (m['lat'] as num?)?.toDouble(),
      lon: (m['lon'] as num?)?.toDouble(),
      distanceKm: (m['distance_km'] as num?)?.toDouble(),
      prices: rawPrices.map((p) => FuelPriceEntry.fromApi(p as Map<String, dynamic>)).toList(),
    );
  }

  double? priceFor(String fuelType) {
    final p = prices.firstWhere(
      (p) => p.fuelType == fuelType,
      orElse: () => const FuelPriceEntry(fuelType: ''),
    );
    return p.priceCents;
  }

  LatLng? get latLng {
    if (lat != null && lon != null) return LatLng(lat!, lon!);
    return null;
  }
}

enum ServoSpyView { map, list }