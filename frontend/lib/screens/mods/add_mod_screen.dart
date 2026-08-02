import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class AddModScreen extends StatefulWidget {
  const AddModScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AddModScreen> createState() => _AddModScreenState();
}

class _AddModScreenState extends State<AddModScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _brand = TextEditingController();
  final _cost = TextEditingController();
  final _date = TextEditingController();
  final _notes = TextEditingController();
  String _category = 'performance';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _date.text = DateTime.now().toString().substring(0, 10);
  }

  @override
  void dispose() {
    for (final c in [_name, _brand, _cost, _date, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      await api.post('/vehicles/${widget.vehicleId}/mods', {
        'name': _name.text,
        'category': _category,
        'brand': _brand.text.isEmpty ? null : _brand.text,
        'cost': double.tryParse(_cost.text) ?? 0.0,
        'install_date': _date.text,
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
      appBar: AppBar(title: const Text('Add modification')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Mod name'),
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _category,
                items: const [
                  DropdownMenuItem(value: 'performance', child: Text('Performance')),
                  DropdownMenuItem(value: 'engine', child: Text('Engine')),
                  DropdownMenuItem(value: 'exhaust', child: Text('Exhaust')),
                  DropdownMenuItem(value: 'suspension', child: Text('Suspension')),
                  DropdownMenuItem(value: 'brakes', child: Text('Brakes')),
                  DropdownMenuItem(value: 'audio', child: Text('Audio')),
                  DropdownMenuItem(value: 'visual', child: Text('Visual')),
                  DropdownMenuItem(value: 'interior', child: Text('Interior')),
                  DropdownMenuItem(value: 'exterior', child: Text('Exterior')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (v) => setState(() => _category = v ?? 'other'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _brand,
                      decoration: const InputDecoration(labelText: 'Brand'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _cost,
                      decoration: const InputDecoration(
                        labelText: 'Cost',
                        prefixText: '\$ ',
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _date,
                decoration: const InputDecoration(labelText: 'Install date'),
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
                child: const Text('Save mod'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
