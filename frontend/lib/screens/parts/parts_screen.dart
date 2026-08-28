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
  final _regoCtrl = TextEditingController();
  final _stateCtrl = TextEditingController(text: 'VIC');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _regoCtrl.dispose();
    _stateCtrl.dispose();
    super.dispose();
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

  Future<void> _lookupSca(BuildContext context) async {
    if (_regoCtrl.text.trim().isEmpty) {
      await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Supercheap Auto parts lookup'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _regoCtrl,
                decoration: const InputDecoration(
                  labelText: 'Registration number (rego)',
                  hintText: 'e.g. ABC123',
                ),
                textCapitalization: TextCapitalization.characters,
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _stateCtrl,
                decoration: const InputDecoration(
                  labelText: 'State',
                  hintText: 'e.g. VIC',
                ),
                textCapitalization: TextCapitalization.characters,
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx),
                       child: const Text('Cancel')),
            FilledButton(
              onPressed: _regoCtrl.text.trim().isEmpty
                  ? null
                  : () => Navigator.pop(ctx),
              child: const Text('Lookup'),
            ),
          ],
        ),
      );
      if (_regoCtrl.text.trim().isEmpty) return;
    }

    final rego = _regoCtrl.text.trim();
    final state = _stateCtrl.text.toUpperCase();
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final data = await api.post(
        '/vehicles/${widget.vehicleId}/parts/sca-lookup', {
        'rego': rego,
        'state': state,
      }) as Map<String, dynamic>;
      final parts = (data['parts'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      if (mounted) await _showScaResults(context, parts);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _showScaResults(
      BuildContext context, List<Map<String, dynamic>> parts) async {
    final selected = <String, Map<String, dynamic>>{};
    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => AlertDialog(
          title: const Text('Supercheap Auto parts'),
          content: SizedBox(
            width: double.maxFinite,
            child: parts.isEmpty
                ? const Text('No parts returned.')
                : ListView.builder(
                    shrinkWrap: true,
                    itemCount: parts.length,
                    itemBuilder: (_, i) {
                      final part = parts[i];
                      final key = part['sku'] as String? ?? part['name'];
                      final isSel = selected.containsKey(key);
                      return CheckboxListTile(
                        value: isSel,
                        onChanged: (v) => setSt(() {
                          if (v == true) {
                            selected[key!] = part;
                          } else {
                            selected.remove(key);
                          }
                        }),
                        title: Text(part['name'] ?? 'Part'),
                        subtitle: Text(part['category'] ?? ''),
                      );
                    },
                  ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Close'),
            ),
            FilledButton(
              onPressed: selected.isEmpty
                  ? null
                  : () async {
                      final api = context.read<AuthState>().api;
                      var added = 0;
                      for (final part in selected.values) {
                        try {
                          await api.post(
                              '/vehicles/${widget.vehicleId}/parts', {
                            'name': part['name'],
                            'sku': part['sku'],
                            'category': part['category'],
                            'quantity': 0,
                            'min_quantity': 1,
                            'supplier': part['supplier'],
                            'notes': part['description'],
                          });
                          added++;
                        } catch (_) {}
                      }
                      if (mounted) Navigator.pop(ctx);
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Added $added part(s) to inventory')),
                        );
                      }
                      _load();
                    },
              child: const Text('Add selected to inventory'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final low = _parts.where((p) => p.needsReorder).toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Parts inventory'),
        actions: [
          IconButton(
            icon: const Icon(Icons.storefront),
            tooltip: 'Look up Supercheap Auto parts',
            onPressed: () => _lookupSca(context),
          ),
        ],
      ),
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
