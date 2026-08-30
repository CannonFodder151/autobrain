part of models;

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
