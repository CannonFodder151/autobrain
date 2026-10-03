import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class AddElectricityScreen extends StatefulWidget {
  const AddElectricityScreen({super.key, required this.vehicleId, this.existing});
  final String vehicleId;
  final ElectricityLog? existing;

  @override
  State<AddElectricityScreen> createState() => _AddElectricityScreenState();
}

class _AddElectricityScreenState extends State<AddElectricityScreen> {
  final _formKey = GlobalKey<FormState>();
  final _date = TextEditingController();
  final _odo = TextEditingController();
  final _kwh = TextEditingController();
  final _price = TextEditingController();
  final _total = TextEditingController();
  final _notes = TextEditingController();
  late bool _fullCharge;
  bool _busy = false;
  String? _receiptId;
  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _date.text = e.chargeDate;
      _odo.text = '${e.odometerKm}';
      _kwh.text = e.kwh.toString();
      _price.text = e.pricePerKwh.toString();
      _total.text = e.totalCost.toString();
      _notes.text = e.notes ?? '';
      _fullCharge = e.isFullCharge;
      _receiptId = e.receiptId;
    } else {
      _date.text = DateTime.now().toString().substring(0, 10);
      _fullCharge = true;
    }
  }

  @override
  void dispose() {
    for (final c in [_date, _odo, _kwh, _price, _total, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  double? get _calcTotal {
    final k = double.tryParse(_kwh.text);
    final p = double.tryParse(_price.text);
    if (k != null && p != null) {
      final t = k * p;
      _total.text = t.toStringAsFixed(2);
      return t;
    }
    return null;
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    final body = <String, dynamic>{
      'charge_date': _date.text,
      'odometer_km': int.parse(_odo.text),
      'kwh': double.parse(_kwh.text),
      'price_per_kwh': double.parse(_price.text),
      'is_full_charge': _fullCharge,
      if (_notes.text.isNotEmpty) 'notes': _notes.text,
      if (_total.text.isNotEmpty && double.tryParse(_total.text) != null)
        'total_cost': double.parse(_total.text),
      if (_receiptId != null) 'receipt_id': _receiptId,
    };
    final api = context.read<AuthState>().api;
    try {
      if (_isEdit) {
        await api.patch(
            '/vehicles/${widget.vehicleId}/electricity/${widget.existing!.id}',
            body);
      } else {
        await api.post('/vehicles/${widget.vehicleId}/electricity', body);
      }
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
      appBar: AppBar(
          title: Text(_isEdit ? 'Edit charge' : 'Add charge')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _date,
                decoration: const InputDecoration(labelText: 'Date'),
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _odo,
                decoration: const InputDecoration(labelText: 'Odometer (km)'),
                keyboardType: TextInputType.number,
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _kwh,
                      decoration: const InputDecoration(labelText: 'kWh'),
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      onChanged: (_) => _calcTotal,
                      validator: (v) =>
                          v == null || v.isEmpty ? 'Required' : null,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _price,
                      decoration: const InputDecoration(
                        labelText: 'Price per kWh',
                        prefixText: '\$ ',
                      ),
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      onChanged: (_) => _calcTotal,
                      validator: (v) =>
                          v == null || v.isEmpty ? 'Required' : null,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _total,
                decoration: const InputDecoration(
                  labelText: 'Total cost (auto)',
                  prefixText: '\$ ',
                ),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _notes,
                decoration:
                    const InputDecoration(labelText: 'Notes (optional)'),
              ),
              const SizedBox(height: 12),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Full charge'),
                value: _fullCharge,
                onChanged: (v) => setState(() => _fullCharge = v ?? true),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(_isEdit ? 'Save changes' : 'Save charge'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
