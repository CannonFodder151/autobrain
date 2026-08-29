import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class AddPartScreen extends StatefulWidget {
  const AddPartScreen({super.key, required this.vehicleId, this.prefill});
  final String vehicleId;
  final Map<String, dynamic>? prefill;

  @override
  State<AddPartScreen> createState() => _AddPartScreenState();
}

class _AddPartScreenState extends State<AddPartScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _sku = TextEditingController();
  final _qty = TextEditingController();
  final _minQty = TextEditingController();
  final _cost = TextEditingController();
  final _supplier = TextEditingController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final p = widget.prefill;
    if (p != null) {
      _name.text = (p['name'] as String?) ?? '';
      _sku.text = (p['sku'] as String?) ?? '';
      _minQty.text = (p['min_quantity'] as int? ?? 1).toString();
      _supplier.text = (p['supplier'] as String?) ?? '';
    }
  }

  @override
  void dispose() {
    for (final c in [_name, _sku, _qty, _minQty, _cost, _supplier]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      await api.post('/vehicles/${widget.vehicleId}/parts', {
        'name': _name.text,
        'sku': _sku.text.isEmpty ? null : _sku.text,
        'quantity': int.tryParse(_qty.text) ?? 0,
        'min_quantity': int.tryParse(_minQty.text) ?? 0,
        'unit_cost': double.tryParse(_cost.text) ?? 0.0,
        'supplier': _supplier.text.isEmpty ? null : _supplier.text,
      });
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Add part')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Part name'),
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _sku,
                decoration: const InputDecoration(labelText: 'SKU / part no.'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _qty,
                      decoration: const InputDecoration(labelText: 'Quantity'),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _minQty,
                      decoration: const InputDecoration(
                        labelText: 'Reorder at',
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _cost,
                      decoration: const InputDecoration(
                        labelText: 'Unit cost',
                        prefixText: '\$ ',
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _supplier,
                      decoration: const InputDecoration(labelText: 'Supplier'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: const Text('Save part'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
