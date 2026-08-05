import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import 'add_vehicle_screen.dart';
import 'edit_vehicle_screen.dart';

class VehicleListScreen extends StatefulWidget {
  const VehicleListScreen({super.key});

  @override
  State<VehicleListScreen> createState() => _VehicleListScreenState();
}

class _VehicleListScreenState extends State<VehicleListScreen> {
  List<Vehicle> _vehicles = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api.get('/vehicles') as List;
      _vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _delete(Vehicle v) async {
    final api = context.read<AuthState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete vehicle?'),
        content: Text('${v.nickname} and all its data will be removed.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await api.delete('/vehicles/${v.id}');
      _load();
    }
  }

  Future<void> _edit(Vehicle v) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => EditVehicleScreen(vehicle: v)),
    );
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final isDemo = context.watch<AuthState>().isDemo;
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicles')),
      floatingActionButton: isDemo
          ? null
          : FloatingActionButton.extended(
              onPressed: () async {
                await Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AddVehicleScreen()),
                );
                _load();
              },
              icon: const Icon(Icons.add),
              label: const Text('Add vehicle'),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                for (final v in _vehicles)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.directions_car),
                      title: Text(v.nickname),
                      subtitle: Text(
                        '${v.make ?? ''} ${v.model ?? ''} ${v.year ?? ''}'
                        '${v.colour != null ? ' · ${v.colour}' : ''}'
                        '${v.rego != null ? ' · ${v.rego}' : ''}'.trim(),
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (v.isPrimary)
                            const Icon(Icons.star, color: Colors.amber),
                          PopupMenuButton<String>(
                            onSelected: (action) {
                              if (action == 'edit') _edit(v);
                              if (action == 'delete') _delete(v);
                            },
                            itemBuilder: (_) => const [
                              PopupMenuItem(
                                  value: 'edit', child: Text('Edit details')),
                              PopupMenuItem(
                                  value: 'delete', child: Text('Delete')),
                            ],
                          ),
                        ],
                      ),
                      onTap: () => _edit(v),
                    ),
                  ),
              ],
            ),
    );
  }
}
