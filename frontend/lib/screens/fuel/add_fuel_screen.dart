import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class AddFuelScreen extends StatefulWidget {
  const AddFuelScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AddFuelScreen> createState() => _AddFuelScreenState();
}

class _AddFuelScreenState extends State<AddFuelScreen> {
  final _formKey = GlobalKey<FormState>();
  final _date = TextEditingController();
  final _odo = TextEditingController();
  final _litres = TextEditingController();
  final _price = TextEditingController();
  bool _fullTank = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _date.text = DateTime.now().toString().substring(0, 10);
  }

  @override
  void dispose() {
    for (final c in [_date, _odo, _litres, _price]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      await api.post('/vehicles/${widget.vehicleId}/fuel', {
        'fill_date': _date.text,
        'odometer_km': int.parse(_odo.text),
        'litres': double.parse(_litres.text),
        'price_per_litre': double.parse(_price.text),
        'is_full_tank': _fullTank,
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
      appBar: AppBar(title: const Text('Add fill-up')),
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
              TextFormField(
                controller: _litres,
                decoration: const InputDecoration(labelText: 'Litres'),
                keyboardType: TextInputType.number,
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _price,
                decoration: const InputDecoration(
                  labelText: 'Price per litre',
                  prefixText: '\$ ',
                ),
                keyboardType: TextInputType.number,
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Full tank'),
                value: _fullTank,
                onChanged: (v) => setState(() => _fullTank = v ?? true),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: const Text('Save fill-up'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
