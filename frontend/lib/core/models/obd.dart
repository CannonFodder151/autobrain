part of models;

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
