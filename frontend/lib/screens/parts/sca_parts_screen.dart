import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class ScaPartsScreen extends StatefulWidget {
  const ScaPartsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ScaPartsScreen> createState() => _ScaPartsScreenState();
}

class _ScaPartsScreenState extends State<ScaPartsScreen> {
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _parts = [];
  List<String> _categories = [];
  Set<int> _selected = {};

  Future<void> _lookup() async {
    setState(() { _loading = true; _error = null; _parts = []; _selected = {}; });
    try {
      final api = context.read<AuthState>().api;
      final data = await api.post(
        '/vehicles/${widget.vehicleId}/parts/sca-lookup',
        const <String, dynamic>{},
      ) as Map<String, dynamic>;
      _parts = (data['parts'] as List? ?? []).cast<Map<String, dynamic>>();
      _categories = (data['service_groups'] as List? ?? []).cast<String>().toList();
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() { _loading = false; });
    }
  }

  Future<void> _import() async {
    final api = context.read<AuthState>().api;
    int imported = 0;
    for (int i = 0; i < _parts.length; i++) {
      if (!_selected.contains(i)) continue;
      final p = _parts[i];
      try {
        await api.post('/vehicles/${widget.vehicleId}/parts', {
          'name': p['name'],
          'sku': p['sku'],
          'category': p['category'] ?? 'other',
          'quantity': p['quantity'] ?? 1,
          'unit_cost': (p['unit_cost'] as num?)?.toDouble() ?? 0.0,
          'supplier': p['supplier'] ?? 'Supercheap Auto',
          'notes': p['notes'],
        });
        imported++;
      } catch (_) {}
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Imported $imported parts')),
      );
      Navigator.pop(context, imported > 0);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('SCA Parts Guide'),
        actions: [
          if (_parts.isNotEmpty)
            FilledButton(
              onPressed: _selected.isEmpty ? null : _import,
              child: Text('Import (${_selected.length})'),
            ),
        ],
      ),
      body: _parts.isEmpty
          ? Center(
              child: _loading
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_error != null) ...[
                          Icon(Icons.error_outline, color: cs.error, size: 48),
                          const SizedBox(height: 8),
                          Text(_error!, style: TextStyle(color: cs.error)),
                          const SizedBox(height: 12),
                        ],
                        FilledButton.icon(
                          onPressed: _lookup,
                          icon: const Icon(Icons.search),
                          label: const Text('Load SCA Parts Guide'),
                        ),
                      ],
                    ),
            )
          : Column(
              children: [
                if (_categories.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Wrap(
                      spacing: 6,
                      children: _categories
                          .map((c) => Chip(label: Text(c, style: const TextStyle(fontSize: 12))))
                          .toList(),
                    ),
                  ),
                Expanded(
                  child: ListView.separated(
                    itemCount: _parts.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final p = _parts[i];
                      return CheckboxListTile(
                        value: _selected.contains(i),
                        onChanged: (v) => setState(() {
                          if (v == true) { _selected.add(i); } else { _selected.remove(i); }
                        }),
                        title: Text(p['name'] ?? ''),
                        subtitle: Text(
                          '${p['service_group'] ?? ''}  '
                          '${p['brand'] != null ? '• ${p['brand']}' : ''}  '
                          '${p['unit_cost'] != null ? '\$${(p['unit_cost'] as num).toStringAsFixed(2)}' : ''}',
                        ),
                        secondary: CircleAvatar(
                          child: Text('${p['quantity'] ?? 1}',
                              style: const TextStyle(fontSize: 14)),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
    );
  }
}
