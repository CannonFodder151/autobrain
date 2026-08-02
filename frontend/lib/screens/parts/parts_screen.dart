import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import 'add_part_screen.dart';

class PartsScreen extends StatefulWidget {
  const PartsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<PartsScreen> createState() => _PartsScreenState();
}

class _PartsScreenState extends State<PartsScreen> {
  List<Part> _parts = const [];
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
      final data =
          await api.get('/vehicles/${widget.vehicleId}/parts') as List;
      _parts = data
          .map((e) => Part.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _adjust(Part p, int delta) async {
    final api = context.read<AuthState>().api;
    try {
      await api.post(
          '/vehicles/${widget.vehicleId}/parts/${p.id}/movement', {
        'delta': delta,
        'reason': delta > 0 ? 'purchase' : 'service',
      });
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
    final low = _parts.where((p) => p.needsReorder).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Parts inventory')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => AddPartScreen(vehicleId: widget.vehicleId),
            ),
          );
          _load();
        },
        icon: const Icon(Icons.add),
        label: const Text('Add part'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (low.isNotEmpty)
                    Card(
                      color: Theme.of(context).colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('AI reorder suggestions',
                                style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onErrorContainer)),
                            for (final p in low)
                              Text(
                                '• ${p.name} — ${p.quantity} in stock (min ${p.minQuantity}), order ${(p.minQuantity * 2 - p.quantity).clamp(1, 999)}',
                                style: TextStyle(
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onErrorContainer),
                              ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 8),
                  for (final p in _parts)
                    Card(
                      child: ListTile(
                        leading: CircleAvatar(
                          child: Text('${p.quantity}',
                              style: const TextStyle(fontSize: 14)),
                        ),
                        title: Text(p.name),
                        subtitle: Text(
                          '${p.category}'
                          '${p.supplier != null ? ' · ${p.supplier}' : ''}'
                          ' · \$${p.unitCost.toStringAsFixed(2)} ea',
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.remove_circle_outline),
                              onPressed: () => _adjust(p, -1),
                            ),
                            IconButton(
                              icon: const Icon(Icons.add_circle_outline),
                              onPressed: () => _adjust(p, 1),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}
