class AdvisorResponse {
  final String module;
  final String? vehicleId;
  final DateTime generatedAt;
  final String model;
  final Map<String, dynamic> data;
  final Map<String, dynamic> factors;

  AdvisorResponse({
    required this.module,
    this.vehicleId,
    required this.generatedAt,
    this.model = 'rule-based-fallback',
    required this.data,
    this.factors = const {},
  });

  factory AdvisorResponse.fromJson(Map<String, dynamic> json) {
    return AdvisorResponse(
      module: json['module'] as String,
      vehicleId: json['vehicle_id'] as String?,
      generatedAt: json['generated_at'] != null
          ? DateTime.parse(json['generated_at'] as String)
          : DateTime.now(),
      model: json['model'] as String? ?? 'rule-based-fallback',
      data: json['data'] as Map<String, dynamic>,
      factors: json['factors'] as Map<String, dynamic>? ?? {},
    );
  }

  Map<String, dynamic> toJson() => {
        'module': module,
        if (vehicleId != null) 'vehicle_id': vehicleId,
        'generated_at': generatedAt.toIso8601String(),
        'model': model,
        'data': data,
        'factors': factors,
      };
}

class ComparableListing {
  final String title;
  final double price;
  final int? year;
  final int? odometerKm;
  final String source;
  final String url;

  ComparableListing({
    this.title = '',
    required this.price,
    this.year,
    this.odometerKm,
    this.source = '',
    this.url = '',
  });

  factory ComparableListing.fromJson(Map<String, dynamic> json) =>
      ComparableListing(
        title: json['title'] as String? ?? '',
        price: (json['price'] as num?)?.toDouble() ?? 0.0,
        year: json['year'] as int?,
        odometerKm: json['odometer_km'] as int?,
        source: json['source'] as String? ?? '',
        url: json['url'] as String? ?? '',
      );
}

class TradeInBand {
  final String currency;
  final double? low;
  final double? mid;
  final double? high;
  final Map<String, double> ratios;

  TradeInBand({
    this.currency = 'AUD',
    this.low,
    this.mid,
    this.high,
    Map<String, double>? ratios,
  }) : ratios = ratios ??
            const {'low': 0.75, 'mid': 0.82, 'high': 0.90};

  factory TradeInBand.fromJson(Map<String, dynamic> json) => TradeInBand(
        currency: json['currency'] as String? ?? 'AUD',
        low: (json['low'] as num?)?.toDouble(),
        mid: (json['mid'] as num?)?.toDouble(),
        high: (json['high'] as num?)?.toDouble(),
        ratios: json['ratios'] != null
            ? Map<String, double>.from(
                (json['ratios'] as Map).map((k, v) =>
                    MapEntry(k as String, (v as num).toDouble())))
            : null,
      );
}

class AdvisorValueData {
  final String currency;
  final double? low;
  final double? mid;
  final double? high;
  final String source;
  final String? asOf;
  final bool stale;
  final int sampleSize;
  final double conditionMultiplier;
  final double kmMultiplier;
  final int comparableCount;
  final int comparableWindowYears;
  final List<ComparableListing> comparables;
  final TradeInBand tradeIn;
  final String? note;

  AdvisorValueData({
    this.currency = 'AUD',
    this.low,
    this.mid,
    this.high,
    this.source = 'fallback',
    this.asOf,
    this.stale = false,
    this.sampleSize = 0,
    this.conditionMultiplier = 1.0,
    this.kmMultiplier = 1.0,
    this.comparableCount = 0,
    this.comparableWindowYears = 3,
    this.comparables = const [],
    required this.tradeIn,
    this.note,
  });

  factory AdvisorValueData.fromJson(Map<String, dynamic> json) =>
      AdvisorValueData(
        currency: json['currency'] as String? ?? 'AUD',
        low: (json['low'] as num?)?.toDouble(),
        mid: (json['mid'] as num?)?.toDouble(),
        high: (json['high'] as num?)?.toDouble(),
        source: json['source'] as String? ?? 'fallback',
        asOf: json['as_of'] as String?,
        stale: json['stale'] as bool? ?? false,
        sampleSize: json['sample_size'] as int? ?? 0,
        conditionMultiplier: (json['condition_multiplier'] as num?)?.toDouble() ?? 1.0,
        kmMultiplier: (json['km_multiplier'] as num?)?.toDouble() ?? 1.0,
        comparableCount: json['comparable_count'] as int? ?? 0,
        comparableWindowYears: json['comparable_window_years'] as int? ?? 3,
        comparables: (json['comparables'] as List?)
                ?.map((e) => ComparableListing.fromJson(e as Map<String, dynamic>))
                .toList() ??
            [],
        tradeIn: json['trade_in'] != null
            ? TradeInBand.fromJson(json['trade_in'] as Map<String, dynamic>)
            : TradeInBand(),
        note: json['note'] as String?,
      );
}

class AmortizationRow {
  final int period;
  final double payment;
  final double interest;
  final double principal;
  final double balanceEnd;

  AmortizationRow({
    required this.period,
    required this.payment,
    required this.interest,
    required this.principal,
    required this.balanceEnd,
  });

  factory AmortizationRow.fromJson(Map<String, dynamic> json) =>
      AmortizationRow(
        period: json['period'] as int,
        payment: (json['payment'] as num).toDouble(),
        interest: (json['interest'] as num).toDouble(),
        principal: (json['principal'] as num).toDouble(),
        balanceEnd: (json['balance_end'] as num).toDouble(),
      );
}

class AdvisorFinanceData {
  final String currency;
  final double vehiclePrice;
  final double downPayment;
  final List<Map<String, dynamic>> modes;
  final String? note;

  AdvisorFinanceData({
    this.currency = 'AUD',
    required this.vehiclePrice,
    required this.downPayment,
    this.modes = const [],
    this.note,
  });

  factory AdvisorFinanceData.fromJson(Map<String, dynamic> json) =>
      AdvisorFinanceData(
        currency: json['currency'] as String? ?? 'AUD',
        vehiclePrice: (json['vehicle_price'] as num).toDouble(),
        downPayment: (json['down_payment'] as num).toDouble(),
        modes: (json['modes'] as List)
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList(),
        note: json['note'] as String?,
      );
}

class AdvisorFinanceRequest {
  final double downPayment;
  final int termMonths;
  final double ratePct;
  final bool novated;

  AdvisorFinanceRequest({
    this.downPayment = 0.0,
    this.termMonths = 60,
    this.ratePct = 7.5,
    this.novated = false,
  });

  Map<String, dynamic> toJson() => {
        'down_payment': downPayment,
        'term_months': termMonths,
        'rate_pct': ratePct,
        'novated': novated,
      };
}

class CarCheckData {
  final String currency;
  final String verdict;
  final double? askingPrice;
  final double? fairValueLow;
  final double? fairValueMid;
  final double? fairValueHigh;
  final double? deltaPct;
  final double? deltaAmount;
  final int sampleSize;
  final double conditionMultiplier;
  final double kmMultiplier;
  final String aiSummary;
  final List<String> redFlags;
  final List<String> greenFlags;
  final String? note;

  CarCheckData({
    this.currency = 'AUD',
    this.verdict = 'risky',
    this.askingPrice,
    this.fairValueLow,
    this.fairValueMid,
    this.fairValueHigh,
    this.deltaPct,
    this.deltaAmount,
    this.sampleSize = 0,
    this.conditionMultiplier = 1.0,
    this.kmMultiplier = 1.0,
    this.aiSummary = '',
    this.redFlags = const [],
    this.greenFlags = const [],
    this.note,
  });

  factory CarCheckData.fromJson(Map<String, dynamic> json) => CarCheckData(
        currency: json['currency'] as String? ?? 'AUD',
        verdict: json['verdict'] as String? ?? 'risky',
        askingPrice: (json['asking_price'] as num?)?.toDouble(),
        fairValueLow: (json['fair_value_low'] as num?)?.toDouble(),
        fairValueMid: (json['fair_value_mid'] as num?)?.toDouble(),
        fairValueHigh: (json['fair_value_high'] as num?)?.toDouble(),
        deltaPct: (json['delta_pct'] as num?)?.toDouble(),
        deltaAmount: (json['delta_amount'] as num?)?.toDouble(),
        sampleSize: json['sample_size'] as int? ?? 0,
        conditionMultiplier: (json['condition_multiplier'] as num?)?.toDouble() ?? 1.0,
        kmMultiplier: (json['km_multiplier'] as num?)?.toDouble() ?? 1.0,
        aiSummary: json['ai_summary'] as String? ?? '',
        redFlags: (json['red_flags'] as List?)?.cast<String>().toList() ?? const [],
        greenFlags: (json['green_flags'] as List?)?.cast<String>().toList() ?? const [],
        note: json['note'] as String?,
      );
}
