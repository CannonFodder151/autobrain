part of models;

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
