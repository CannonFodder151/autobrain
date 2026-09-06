import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/models.dart';
import '../../widgets/stale_hint.dart';
import 'add_part_screen.dart';
import 'sca_lookup_results_screen.dart';

class PartsScreen extends StatefulWidget {
  const PartsScreen({super.key, required this.vehicle});
  final Vehicle vehicle;

  @override
  State<PartsScreen> createState() => _PartsScreenState();
}

class _PartsScreenState extends State<PartsScreen> {
  List<Part> _parts = const [];
  bool _loading = true;
  bool _stale = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    super.dispose();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    final path = '/vehicles/${widget.vehicle.id}/parts';
    final q = <String, String>? null;
    final cached = await api.getCachedDecoded(path, q);
    if (cached != null) {
      _parts = (cached as List)
          .map((e) => Part.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = true;
      if (!mounted) return;
      setState(() => _loading = false);
    }
    if (!mounted) return;
    if (!ConnectivityService.instance.isOnline) return;
    try {
      final data = await api.get(path) as List;
      _parts = data
          .map((e) => Part.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = false;
    } catch (_) {
      if (_parts.isEmpty) _stale = true;
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _adjust(Part p, int delta) async {
    final api = context.read<AuthState>().api;
    try {
      await api.post(
          '/vehicles/${widget.vehicle.id}/parts/${p.id}/movement', {
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
    // AUT-1903: drive the lookup from the selected vehicle's plate + state
    // rather than letting the user type a rego.
    final rego = (widget.vehicle.rego ?? '').trim();
    if (rego.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Add a rego to this vehicle to look up parts.'),
        ));
      }
      return;
    }
    final state = (widget.vehicle.regoState ?? 'VIC').toUpperCase();
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ScaLookupResultsScreen(
          vehicleId: widget.vehicle.id,
          rego: rego,
          state: state,
        ),
      ),
    );
    if (mounted) _load();
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
              builder: (_) => AddPartScreen(vehicleId: widget.vehicle.id),
            ),
          );
          _load();
        },
        icon: const Icon(Icons.add),
        label: const Text('Add part'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading && _parts.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  StaleHint(
                    isStale: _stale,
                    isOffline: !ConnectivityService.instance.isOnline,
                  ),
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
