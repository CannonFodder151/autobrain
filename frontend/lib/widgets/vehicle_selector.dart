import 'package:flutter/material.dart';

import '../core/models.dart';

class VehicleSelector extends StatelessWidget {
  const VehicleSelector({
    super.key,
    required this.vehicles,
    required this.selected,
    required this.onChanged,
    required this.onManage,
  });

  final List<Vehicle> vehicles;
  final Vehicle? selected;
  final ValueChanged<Vehicle> onChanged;
  final VoidCallback onManage;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: vehicles.isEmpty
              ? const Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('No vehicles yet'),
                  ),
                )
              : DropdownButtonFormField<Vehicle>(
                  value: selected,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Vehicle',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final v in vehicles)
                      DropdownMenuItem(value: v, child: Text(v.dropdownLabel)),
                  ],
                  onChanged: (v) {
                    if (v != null) onChanged(v);
                  },
                ),
        ),
        const SizedBox(width: 8),
        IconButton.filledTonal(
          onPressed: onManage,
          icon: const Icon(Icons.add),
          tooltip: 'Manage vehicles',
        ),
      ],
    );
  }
}
