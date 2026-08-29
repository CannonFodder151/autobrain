import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import 'add_part_screen.dart';

/// AUT-1903: pages the SCA parts lookup into its own screen. The vehicle's
/// plate + state drive the lookup (no rego text entry), and the AI-normalised
/// result set is shown on a full screen sorted by category then name.
class ScaLookupResultsScreen extends StatefulWidget {
  const ScaLookupResultsScreen({
    super.key,
    required this.vehicleId,
    required this.rego,
    required this.state,
  });

  final String vehicleId;
  final String rego;
  final String state;

  @override
  State<ScaLookupResultsScreen> createState() => _ScaLookupResultsScreenState();
}

class _ScaLookupResultsScreenState extends State<ScaLookupResultsScreen> {
  bool _loading = true;
  String? _note;
  String? _model;
  List<Map<String, dynamic>> _parts = [];

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api.post(
        '/vehicles/${widget.vehicleId}/parts/sca-lookup',
        {
          'rego': widget.rego,
          'state': widget.state,
        },
      ) as Map<String, dynamic>;
      final parts = (data['parts'] as List? ?? [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      parts.sort(_sortByName);
      setState(() {
        _note = data['note'] as String?;
        _model = data['model'] as String?;
        _parts = parts;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  static int _sortByName(Map<String, dynamic> a, Map<String, dynamic> b) {
    final ac = (a['category'] as String? ?? '').compareTo(
        (b['category'] as String? ?? ''));
    if (ac != 0) return ac;
    return (a['name'] as String? ?? '')
        .compareTo(b['name'] as String? ?? '');
  }

  Future<void> _addSelected(Map<String, Map<String, dynamic>> selected) async {
    final api = context.read<AuthState>().api;
    var added = 0;
    for (final part in selected.values) {
      try {
        await api.post('/vehicles/${widget.vehicleId}/parts', {
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
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Added $added part(s) to inventory')));
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final money = NumberFormat.currency(locale: 'en_AU', symbol: '\$');
    final subtitleStyle = TextStyle(
      color: Theme.of(context).colorScheme.onSurfaceVariant,
    );
    return Scaffold(
      appBar: AppBar(
        title: const Text('Supercheap Auto parts'),
        actions: [
          if (_parts.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.add_shopping_cart),
              tooltip: 'Add selected to inventory',
              onPressed: () async {
                final selected = await _showSelectSheet();
                if (selected != null && selected.isNotEmpty) {
                  await _addSelected(selected);
                }
              },
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _parts.isEmpty
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      _note ?? 'No parts returned.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Theme.of(context)
                            .colorScheme
                            .onSurfaceVariant,
                      ),
                    ),
                  ),
                )
              : ListView.separated(
                  itemCount: _parts.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final part = _parts[i];
                    final name = part['name'] as String? ?? 'Part';
                    final category = part['category'] as String? ?? '';
                    final supplier = part['supplier'] as String?;
                    final sku = part['sku'] as String?;
                    final unitCost = part['unit_cost'];
                    final price = unitCost is num ? money.format(unitCost) : '';
                    return ListTile(
                      title: Text(name),
                      subtitle: Text(
                        [category, supplier, price, sku]
                            .where((e) => e != null && e.isNotEmpty)
                            .join(' · '),
                        style: subtitleStyle,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: sku != null && sku.isNotEmpty
                          ? Icon(Icons.chevron_right,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant)
                          : null,
                      onTap: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => AddPartScreen(
                              vehicleId: widget.vehicleId,
                              prefill: part,
                            ),
                          ),
                        );
                      },
                    );
                  },
                ),
      bottomNavigationBar: _parts.isEmpty || _loading
          ? null
          : Padding(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Wrap(
                spacing: 8,
                children: [
                  if (_model != null)
                    Chip(
                      label: Text('Normalised by: $_model',
                          style: TextStyle(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSecondaryContainer)),
                      backgroundColor: Theme.of(context)
                          .colorScheme
                          .secondaryContainer,
                    ),
                  if (_note != null)
                    Chip(
                      label: Text('Note: $_note',
                          style: TextStyle(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onErrorContainer)),
                      backgroundColor: Theme.of(context)
                          .colorScheme
                          .errorContainer,
                    ),
                ],
              ),
            ),
    );
  }

  Future<Map<String, Map<String, dynamic>>?> _showSelectSheet() {
    final selected = <String, Map<String, dynamic>>{};
    return showModalBottomSheet<Map<String, Map<String, dynamic>>>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setSt) => SizedBox(
            height: MediaQuery.of(ctx).size.height * 0.6,
            child: Column(
              children: [
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('${selected.length} selected',
                          style: Theme.of(ctx).textTheme.titleMedium),
                      TextButton(
                          onPressed: () => Navigator.pop(ctx),
                          child: const Text('Done')),
                    ],
                  ),
                ),
                Expanded(
                  child: ListView.builder(
                    itemCount: _parts.length,
                    itemBuilder: (_, i) {
                      final part = _parts[i];
                      final key =
                          part['sku'] as String? ?? part['name'] as String;
                      final isSel = selected.containsKey(key);
                      return CheckboxListTile(
                        value: isSel,
                        onChanged: (v) => setSt(() {
                          if (v == true) {
                            selected[key] = part;
                          } else {
                            selected.remove(key);
                          }
                        }),
                        title: Text(part['name'] as String? ?? 'Part'),
                        subtitle: Text(part['category'] as String? ?? ''),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
