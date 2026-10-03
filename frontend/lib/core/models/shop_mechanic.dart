part of models;

class ShopMechanic {
  final String id;
  final String name;
  final String? address;
  final double? lat;
  final double? lon;
  final double? distanceKm;
  final double? rating;
  final int? reviewCount;
  final List<String> services;
  final String? phoneNumber;
  final String? logoUrl;
  final bool? isOpen;

  const ShopMechanic({
    required this.id,
    required this.name,
    this.address,
    this.lat,
    this.lon,
    this.distanceKm,
    this.rating,
    this.reviewCount,
    this.services = const [],
    this.phoneNumber,
    this.logoUrl,
    this.isOpen,
  });

  factory ShopMechanic.fromJson(Map<String, dynamic> j) => ShopMechanic(
        id: j['id'] as String? ?? '',
        name: j['name'] as String? ?? 'Unknown',
        address: j['address'] as String?,
        lat: (j['lat'] as num?)?.toDouble(),
        lon: (j['lon'] as num?)?.toDouble(),
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        rating: (j['rating'] as num?)?.toDouble(),
        reviewCount: (j['review_count'] as num?)?.toInt(),
        services: ((j['services'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        phoneNumber: j['phone_number'] as String?,
        logoUrl: j['logo_url'] as String?,
        isOpen: j['is_open'] as bool?,
      );
}
