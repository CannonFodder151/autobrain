import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/models.dart';
import 'add_mod_screen.dart';

class ModsScreen extends StatefulWidget {
  const ModsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ModsScreen> createState() => _ModsScreenState();
}

class _ModsScreenState extends State<ModsScreen> {
  List<Modification> _mods = const [];
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
      final data = await api.get('/vehicles/${widget.vehicleId}/mods') as List;
      _mods = data
          .map((e) => Modification.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _export(String fmt) async {
    final api = context.read<AuthState>().api;
    try {
      final bytes = await api.export(
          '/vehicles/${widget.vehicleId}/mods/export?fmt=$fmt');
      await downloadBytes('build-sheet.$fmt', bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Export failed: $e')));
      }
    }
  }

  Future<void> _edit(Modification m) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AddModScreen(vehicleId: widget.vehicleId, mod: m),
      ),
    );
    _load();
  }

  Future<void> _delete(Modification m) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete mod?'),
        content: Text('${m.name} will be removed from the build sheet.'),
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
    if (ok != true) return;
    final api = context.read<AuthState>().api;
    try {
      await api.delete('/vehicles/${widget.vehicleId}/mods/${m.id}');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final total = _mods.fold<double>(0, (a, b) => a + b.cost);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Modifications'),
        actions: [
          PopupMenuButton<String>(
            onSelected: _export,
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'csv', child: Text('Export CSV')),
              PopupMenuItem(value: 'pdf', child: Text('Export PDF')),
            ],
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => AddModScreen(vehicleId: widget.vehicleId),
            ),
          );
          _load();
        },
        icon: const Icon(Icons.add),
        label: const Text('Add mod'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.payments),
                      title: const Text('Total build spend'),
                      trailing: Text(
                        '\$${total.toStringAsFixed(0)}',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final m in _mods)
                    Card(
                      child: ListTile(
                        leading: const Icon(Icons.tune),
                        title: Text(m.name),
                        subtitle: Text(
                          '${m.category}'
                          '${m.brand != null ? ' · ${m.brand}' : ''}'
                          '${m.installDate != null ? ' · ${m.installDate}' : ''}',
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text('\$${m.cost.toStringAsFixed(0)}'),
                            PopupMenuButton<String>(
                              onSelected: (action) {
                                if (action == 'edit') _edit(m);
                                if (action == 'delete') _delete(m);
                              },
                              itemBuilder: (_) => const [
                                PopupMenuItem(
                                    value: 'edit', child: Text('Edit')),
                                PopupMenuItem(
                                    value: 'delete', child: Text('Delete')),
                              ],
                            ),
                          ],
                        ),
                        onTap: () => _edit(m),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}
