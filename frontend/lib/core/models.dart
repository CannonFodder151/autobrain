/// Typed models mirroring the backend API schemas.
library models;

class Vehicle {
  final String id;
  final String nickname;
  final String? rego, vin, make, model, colour, bodyType, engine, transmission;
  final int? year, odometerKm;
  final String condition;
  final String vehicleType;
  final bool isPrimary, clubReg;

  const Vehicle({
    required this.id,
    required this.nickname,
    this.rego,
    this.vin,
    this.make,
    this.model,
    this.colour,
    this.bodyType,
    this.engine,
    this.transmission,
    this.year,
    this.odometerKm,
    this.condition = 'good',
    this.vehicleType = 'car',
    this.isPrimary = false,
    this.clubReg = false,
  });

  String get displayName => '$nickname'
      '${make != null ? ' ($make $model)' : ''}'.trim();

  factory Vehicle.fromJson(Map<String, dynamic> j) => Vehicle(
        id: j['id'] as String,
        nickname: j['nickname'] as String,
        rego: j['rego'] as String?,
        vin: j['vin'] as String?,
        make: j['make'] as String?,
        model: j['model'] as String?,
        colour: j['colour'] as String?,
        bodyType: j['body_type'] as String?,
        engine: j['engine'] as String?,
        transmission: j['transmission'] as String?,
        year: j['year'] as int?,
        odometerKm: j['odometer_km'] as int?,
        condition: (j['condition'] as String?) ?? 'good',
        vehicleType: (j['vehicle_type'] as String?) ?? 'car',
        isPrimary: (j['is_primary'] as bool?) ?? false,
        clubReg: (j['club_reg'] as bool?) ?? false,
      );
}

class TimelineEvent {
  final String id, eventType, title;
  final String occurredOn;
  final int? odometerKm;
  final double? amount;

  const TimelineEvent({
    required this.id,
    required this.eventType,
    required this.title,
    required this.occurredOn,
    this.odometerKm,
    this.amount,
  });

  factory TimelineEvent.fromJson(Map<String, dynamic> j) => TimelineEvent(
        id: j['id'] as String,
        eventType: j['event_type'] as String,
        title: j['title'] as String,
        occurredOn: j['occurred_on'] as String,
        odometerKm: j['odometer_km'] as int?,
        amount: (j['amount'] as num?)?.toDouble(),
      );
}

class ServiceItem {
  final String id;
  final String name;
  final int quantity;
  final double unitCost;
  final String kind;
  final String? partNo;
  final String? partId;

  const ServiceItem({
    required this.id,
    required this.name,
    this.quantity = 1,
    this.unitCost = 0,
    this.kind = 'item',
    this.partNo,
    this.partId,
  });

  double get total => quantity * unitCost;

  factory ServiceItem.fromJson(Map<String, dynamic> j) => ServiceItem(
        id: j['id'] as String,
        name: j['name'] as String,
        quantity: (j['quantity'] as num?)?.toInt() ?? 1,
        unitCost: (j['unit_cost'] as num?)?.toDouble() ?? 0,
        kind: j['kind'] as String? ?? 'item',
        partNo: j['part_no'] as String?,
        partId: j['part_id'] as String?,
      );
}

class ServiceRecord {
  final String id;
  final String serviceDate;
  final int odometerKm;
  final String serviceType;
  final String? description, workshop, notes;
  final double cost;
  final int? nextDueKm;
  final String? nextDueDate;
  final String status; // scheduled/completed
  final String? completedDate;
  final List<String> steps;
  final List<ServiceItem> items;

  const ServiceRecord({
    required this.id,
    required this.serviceDate,
    required this.odometerKm,
    required this.serviceType,
    this.description,
    this.workshop,
    this.notes,
    this.cost = 0,
    this.nextDueKm,
    this.nextDueDate,
    this.status = 'completed',
    this.completedDate,
    this.steps = const [],
    this.items = const [],
  });

  bool get isScheduled => status == 'scheduled';

  factory ServiceRecord.fromJson(Map<String, dynamic> j) => ServiceRecord(
        id: j['id'] as String,
        serviceDate: j['service_date'] as String,
        odometerKm: j['odometer_km'] as int,
        serviceType: j['service_type'] as String,
        description: j['description'] as String?,
        workshop: j['workshop'] as String?,
        notes: j['notes'] as String?,
        cost: (j['cost'] as num?)?.toDouble() ?? 0,
        nextDueKm: j['next_due_km'] as int?,
        nextDueDate: j['next_due_date'] as String?,
        status: j['status'] as String? ?? 'completed',
        completedDate: j['completed_date'] as String?,
        steps: ((j['steps'] as List?) ?? []).map((e) => e.toString()).toList(),
        items: ((j['items'] as List?) ?? [])
            .map((e) => ServiceItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class FuelLog {
  final String id;
  final String fillDate;
  final int odometerKm;
  final double litres, pricePerLitre, totalCost;
  final bool isFullTank;
  final double? lPer100km, costPerKm;
  final String? notes, receiptId;

  const FuelLog({
    required this.id,
    required this.fillDate,
    required this.odometerKm,
    required this.litres,
    required this.pricePerLitre,
    required this.totalCost,
    this.isFullTank = true,
    this.lPer100km,
    this.costPerKm,
    this.notes,
    this.receiptId,
  });

  factory FuelLog.fromJson(Map<String, dynamic> j) => FuelLog(
        id: j['id'] as String,
        fillDate: j['fill_date'] as String,
        odometerKm: j['odometer_km'] as int,
        litres: (j['litres'] as num).toDouble(),
        pricePerLitre: (j['price_per_litre'] as num).toDouble(),
        totalCost: (j['total_cost'] as num).toDouble(),
        isFullTank: (j['is_full_tank'] as bool?) ?? true,
        lPer100km: (j['l_per_100km'] as num?)?.toDouble(),
        costPerKm: (j['cost_per_km'] as num?)?.toDouble(),
        notes: j['notes'] as String?,
        receiptId: j['receipt_id'] as String?,
      );
}

class Diagnostic {
  final String id, symptoms;
  final String? summary, severity;
  final double? estimatedCost;
  final bool addedToService;
  final String status; // open/resolved
  final String? linkedServiceId;

  const Diagnostic({
    required this.id,
    required this.symptoms,
    this.summary,
    this.severity,
    this.estimatedCost,
    this.addedToService = false,
    this.status = 'open',
    this.linkedServiceId,
  });

  bool get isResolved => status == 'resolved';

  factory Diagnostic.fromJson(Map<String, dynamic> j) => Diagnostic(
        id: j['id'] as String,
        symptoms: j['symptoms'] as String,
        summary: j['summary'] as String?,
        severity: j['severity'] as String?,
        estimatedCost: (j['estimated_cost'] as num?)?.toDouble(),
        addedToService: (j['added_to_service'] as bool?) ?? false,
        status: j['status'] as String? ?? 'open',
        linkedServiceId: j['linked_service_id'] as String?,
      );
}

class LogEntry {
  final String id;
  final String? startedAt, endedAt;
  final int? startOdometerKm, endOdometerKm;
  final double? distanceKm;
  final String purpose; // work/private
  final String? reason;
  final String? startLocation, endLocation;
  final double? startLat, startLng, endLat, endLng;
  final String status; // in_progress/completed

  const LogEntry({
    required this.id,
    this.startedAt,
    this.endedAt,
    this.startOdometerKm,
    this.endOdometerKm,
    this.distanceKm,
    this.purpose = 'private',
    this.reason,
    this.startLocation,
    this.endLocation,
    this.startLat,
    this.startLng,
    this.endLat,
    this.endLng,
    this.status = 'in_progress',
  });

  bool get isComplete => status == 'completed';

  factory LogEntry.fromJson(Map<String, dynamic> j) => LogEntry(
        id: j['id'] as String,
        startedAt: j['started_at'] as String?,
        endedAt: j['ended_at'] as String?,
        startOdometerKm: j['start_odometer_km'] as int?,
        endOdometerKm: j['end_odometer_km'] as int?,
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        purpose: j['purpose'] as String? ?? 'private',
        reason: j['reason'] as String?,
        startLocation: j['start_location'] as String?,
        endLocation: j['end_location'] as String?,
        startLat: (j['start_lat'] as num?)?.toDouble(),
        startLng: (j['start_lng'] as num?)?.toDouble(),
        endLat: (j['end_lat'] as num?)?.toDouble(),
        endLng: (j['end_lng'] as num?)?.toDouble(),
        status: j['status'] as String? ?? 'in_progress',
      );
}

class ObdCode {
  final String id, code;
  final String? description;
  final bool isResolved;
  final String source;

  const ObdCode({
    required this.id,
    required this.code,
    this.description,
    this.isResolved = false,
    this.source = 'obd',
  });

  factory ObdCode.fromJson(Map<String, dynamic> j) => ObdCode(
        id: j['id'] as String,
        code: j['code'] as String,
        description: j['description'] as String?,
        isResolved: (j['is_resolved'] as bool?) ?? false,
        source: j['source'] as String? ?? 'obd',
      );
}

class Modification {
  final String id, name, category;
  final String? brand, notes;
  final double cost;
  final String? installDate;

  const Modification({
    required this.id,
    required this.name,
    required this.category,
    this.brand,
    this.notes,
    this.cost = 0,
    this.installDate,
  });

  factory Modification.fromJson(Map<String, dynamic> j) => Modification(
        id: j['id'] as String,
        name: j['name'] as String,
        category: j['category'] as String,
        brand: j['brand'] as String?,
        notes: j['notes'] as String?,
        cost: (j['cost'] as num?)?.toDouble() ?? 0,
        installDate: j['install_date'] as String?,
      );
}

class Part {
  final String id, name, category;
  final int quantity, minQuantity;
  final double unitCost;
  final String? sku, supplier, aiReorderSuggestion;

  const Part({
    required this.id,
    required this.name,
    required this.category,
    required this.quantity,
    required this.minQuantity,
    this.unitCost = 0,
    this.sku,
    this.supplier,
    this.aiReorderSuggestion,
  });

  bool get needsReorder => quantity <= minQuantity;

  factory Part.fromJson(Map<String, dynamic> j) => Part(
        id: j['id'] as String,
        name: j['name'] as String,
        category: j['category'] as String,
        quantity: (j['quantity'] as num?)?.toInt() ?? 0,
        minQuantity: (j['min_quantity'] as num?)?.toInt() ?? 0,
        unitCost: (j['unit_cost'] as num?)?.toDouble() ?? 0,
        sku: j['sku'] as String?,
        supplier: j['supplier'] as String?,
        aiReorderSuggestion: j['ai_reorder_suggestion'] as String?,
      );
}

class Receipt {
  final String id;
  final String? originalName, vendor;
  final String ocrStatus;
  final double? total;

  const Receipt({
    required this.id,
    this.originalName,
    this.vendor,
    this.ocrStatus = 'pending',
    this.total,
  });

  factory Receipt.fromJson(Map<String, dynamic> j) => Receipt(
        id: j['id'] as String,
        originalName: j['original_name'] as String?,
        vendor: j['vendor'] as String?,
        ocrStatus: j['ocr_status'] as String? ?? 'pending',
        total: (j['total'] as num?)?.toDouble(),
      );
}

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

class ServicePrediction {
  final String serviceType;
  final int intervalKm, dueInKm, nextDueKm;
  final String nextDueDate;
  final double confidence;
  final String reason;

  const ServicePrediction({
    required this.serviceType,
    required this.intervalKm,
    required this.dueInKm,
    required this.nextDueDate,
    required this.confidence,
    required this.reason,
    this.nextDueKm = 0,
  });

  factory ServicePrediction.fromJson(Map<String, dynamic> j) =>
      ServicePrediction(
        serviceType: j['service_type'] as String,
        intervalKm: (j['interval_km'] as num).toInt(),
        dueInKm: (j['due_in_km'] as num).toInt(),
        nextDueDate: j['next_due_date'] as String,
        confidence: (j['confidence'] as num).toDouble(),
        reason: j['reason'] as String,
        nextDueKm: (j['next_due_km'] as num?)?.toInt() ?? 0,
      );
}
