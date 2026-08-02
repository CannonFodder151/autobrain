import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class AddServiceScreen extends StatefulWidget {
  const AddServiceScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AddServiceScreen> createState() => _AddServiceScreenState();
}

class _AddServiceScreenState extends State<AddServiceScreen> {
  final _formKey = GlobalKey<FormState>();
  final _date = TextEditingController();
  final _odometer = TextEditingController();
  final _workshop = TextEditingController();
  final _cost = TextEditingController();
  final _notes = TextEditingController();
  String _type = 'scheduled';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _date.text = DateTime.now().toString().substring(0, 10);
  }

  @override
  void dispose() {
    for (final c in [_date, _odometer, _workshop, _cost, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      await api.post('/vehicles/${widget.vehicleId}/services', {
        'service_date': _date.text,
        'odometer_km': int.parse(_odometer.text),
        'service_type': _type,
        'workshop': _workshop.text.isEmpty ? null : _workshop.text,
        'cost': double.tryParse(_cost.text) ?? 0.0,
        'notes': _notes.text.isEmpty ? null : _notes.text,
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
      appBar: AppBar(title: const Text('Log service')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                value: _type,
                decoration: const InputDecoration(labelText: 'Service type'),
                items: const [
                  DropdownMenuItem(value: 'scheduled', child: Text('Scheduled')),
                  DropdownMenuItem(value: 'oil_change', child: Text('Oil change')),
                  DropdownMenuItem(value: 'repair', child: Text('Repair')),
                  DropdownMenuItem(value: 'tire', child: Text('Tyres')),
                  DropdownMenuItem(value: 'custom', child: Text('Custom')),
                ],
                onChanged: (v) => setState(() => _type = v ?? 'scheduled'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _date,
                decoration: const InputDecoration(labelText: 'Date'),
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _odometer,
                decoration: const InputDecoration(labelText: 'Odometer (km)'),
                keyboardType: TextInputType.number,
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _workshop,
                decoration: const InputDecoration(labelText: 'Workshop'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _cost,
                decoration: const InputDecoration(
                  labelText: 'Cost',
                  prefixText: '\$ ',
                ),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _notes,
                decoration: const InputDecoration(labelText: 'Notes'),
                maxLines: 3,
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: const Text('Save service'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
