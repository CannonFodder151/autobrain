part of models;

class MarketListing {
  final String title;
  final double? price;
  final int? year;
  final int? odometerKm;
  final String source;
  final String url;

  const MarketListing({
    this.title = '',
    this.price,
    this.year,
    this.odometerKm,
    this.source = '',
    this.url = '',
  });

  factory MarketListing.fromJson(Map<String, dynamic> j) => MarketListing(
        title: j['title'] as String? ?? '',
        price: (j['price'] as num?)?.toDouble(),
        year: j['year'] as int?,
        odometerKm: j['odometer_km'] as int?,
        source: j['source'] as String? ?? '',
        url: j['url'] as String? ?? '',
      );
}

class MarketData {
  final String query, source;
  final List<MarketListing> listings;
  final double? medianPrice, lowPrice, highPrice;
  final int sampleSize;
  final bool stale;

  const MarketData({
    this.query = '',
    this.source = 'fallback',
    this.listings = const [],
    this.medianPrice,
    this.lowPrice,
    this.highPrice,
    this.sampleSize = 0,
    this.stale = false,
  });

  bool get hasData => sampleSize > 0 && medianPrice != null;

  factory MarketData.fromJson(Map<String, dynamic> j) => MarketData(
        query: j['query'] as String? ?? '',
        source: j['source'] as String? ?? 'fallback',
        listings: ((j['listings'] as List?) ?? [])
            .map((e) => MarketListing.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        medianPrice: (j['median_price'] as num?)?.toDouble(),
        lowPrice: (j['low_price'] as num?)?.toDouble(),
        highPrice: (j['high_price'] as num?)?.toDouble(),
        sampleSize: j['sample_size'] as int? ?? 0,
        stale: j['stale'] as bool? ?? false,
      );
}

class Valuation {
  final double estimatedValue, low, high;
  final List<String> recommendations;
  final Map<String, dynamic> factors;
  final String model;
  final MarketData? market;

  const Valuation({
    required this.estimatedValue,
    required this.low,
    required this.high,
    this.recommendations = const [],
    this.factors = const {},
    this.model = '',
    this.market,
  });

  factory Valuation.fromJson(Map<String, dynamic> j) => Valuation(
        estimatedValue: (j['estimated_value'] as num).toDouble(),
        low: (j['low'] as num).toDouble(),
        high: (j['high'] as num).toDouble(),
        recommendations: ((j['recommendations'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        factors: (j['factors'] as Map?)?.cast<String, dynamic>() ?? {},
        model: j['model'] as String? ?? '',
        market: j['market'] is Map
            ? MarketData.fromJson((j['market'] as Map).cast<String, dynamic>())
            : null,
      );
}
