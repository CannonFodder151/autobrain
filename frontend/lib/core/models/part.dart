part of models;

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
