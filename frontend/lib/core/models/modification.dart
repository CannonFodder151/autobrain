part of models;

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
