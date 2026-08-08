part of models;

class Valuation {
  final double estimatedValue, low, high;
  final List<String> recommendations;
  final Map<String, dynamic> factors;
  final String model;

  const Valuation({
    required this.estimatedValue,
    required this.low,
    required this.high,
    this.recommendations = const [],
    this.factors = const {},
    this.model = '',
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
      );
}
