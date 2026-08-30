part of models;

class Analytics {
  final SpendSummary summary;
  final List<MonthlySpend> monthly;
  final List<String> insights;
  final CostForecast forecast;

  const Analytics({
    required this.summary,
    required this.monthly,
    required this.insights,
    this.forecast = const CostForecast(),
  });

  factory Analytics.fromJson(Map<String, dynamic> j) => Analytics(
        summary: SpendSummary.fromJson(j['summary'] as Map<String, dynamic>),
        monthly: ((j['monthly'] as List?) ?? [])
            .map((e) => MonthlySpend.fromJson(e as Map<String, dynamic>))
            .toList(),
        insights: ((j['insights'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        forecast: CostForecast.fromJson(
            (j['forecast'] as Map<String, dynamic>?) ?? {}),
      );
}

class CostForecast {
  final double next12Months;
  final String basis;
  final double confidence;

  const CostForecast({
    this.next12Months = 0,
    this.basis = '',
    this.confidence = 0,
  });

  factory CostForecast.fromJson(Map<String, dynamic> j) => CostForecast(
        next12Months: (j['next_12_months'] as num?)?.toDouble() ?? 0,
        basis: j['basis'] as String? ?? '',
        confidence: (j['confidence'] as num?)?.toDouble() ?? 0,
      );
}

class SpendSummary {
  final double fuelTotal, serviceTotal, modTotal, totalCostOfOwnership;
  final double? costPerKm;

  const SpendSummary({
    required this.fuelTotal,
    required this.serviceTotal,
    required this.modTotal,
    required this.totalCostOfOwnership,
    this.costPerKm,
  });

  factory SpendSummary.fromJson(Map<String, dynamic> j) => SpendSummary(
        fuelTotal: (j['fuel_total'] as num?)?.toDouble() ?? 0,
        serviceTotal: (j['service_total'] as num?)?.toDouble() ?? 0,
        modTotal: (j['mod_total'] as num?)?.toDouble() ?? 0,
        totalCostOfOwnership:
            (j['total_cost_of_ownership'] as num?)?.toDouble() ?? 0,
        costPerKm: (j['cost_per_km'] as num?)?.toDouble(),
      );
}

class MonthlySpend {
  final String month;
  final double fuel, service, mod;

  const MonthlySpend({
    required this.month,
    required this.fuel,
    required this.service,
    required this.mod,
  });

  factory MonthlySpend.fromJson(Map<String, dynamic> j) => MonthlySpend(
        month: j['month'] as String,
        fuel: (j['fuel'] as num?)?.toDouble() ?? 0,
        service: (j['service'] as num?)?.toDouble() ?? 0,
        mod: (j['mod'] as num?)?.toDouble() ?? 0,
      );
}
