part of models;

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
