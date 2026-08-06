import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class EditVehicleScreen extends StatefulWidget {
  const EditVehicleScreen({super.key, required this.vehicle});

  final Vehicle vehicle;

  @override
  State<EditVehicleScreen> createState() => _EditVehicleScreenState();
}

class _EditVehicleScreenState extends State<EditVehicleScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nickname;
  late final TextEditingController _rego;
  late final TextEditingController _vin;
  late final TextEditingController _make;
  late final TextEditingController _model;
  late final TextEditingController _colour;
  late final TextEditingController _bodyType;
  late final TextEditingController _engine;
  late final TextEditingController _transmission;
  late final TextEditingController _odometer;
  int? _year;
  String _state = 'VIC';
  String _vehicleType = 'car';
  bool _busy = false;
  bool _isPrimary = false;
  bool _clubReg = false;
  bool _lookingUp = false;
  String? _lookupInfo;

  @override
  void initState() {
    super.initState();
    final v = widget.vehicle;
    _nickname = TextEditingController(text: v.nickname);
    _rego = TextEditingController(text: v.rego ?? '');
    _vin = TextEditingController(text: v.vin ?? '');
    _make = TextEditingController(text: v.make ?? '');
    _model = TextEditingController(text: v.model ?? '');
    _colour = TextEditingController(text: v.colour ?? '');
    _bodyType = TextEditingController(text: v.bodyType ?? '');
    _engine = TextEditingController(text: v.engine ?? '');
    _transmission = TextEditingController(text: v.transmission ?? '');
    _odometer = TextEditingController(text: '${v.odometerKm ?? ''}');
    _year = v.year;
    _vehicleType = v.vehicleType;
    _isPrimary = v.isPrimary;
    _clubReg = v.clubReg;
  }

  @override
  void dispose() {
    for (final c in [
      _nickname, _rego, _vin, _make, _model, _colour, _bodyType, _engine, _transmission, _odometer
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _lookup() async {
    if (_rego.text.trim().isEmpty) return;
    setState(() {
      _lookingUp = true;
      _lookupInfo = null;
    });
    try {
      final api = context.read<AuthState>().api;
      final r = await api.post('/vehicles/rego-lookup', {
        'rego': _rego.text.trim(),
        'jurisdiction': 'AU',
        'state': _state,
        'vehicle_type': _vehicleType,
      }) as Map<String, dynamic>;
      setState(() {
        _vin.text = (r['vin'] as String?) ?? _vin.text;
        _make.text = (r['make'] as String?) ?? _make.text;
        _model.text = (r['model'] as String?) ?? _model.text;
        _colour.text = (r['colour'] as String?) ?? _colour.text;
        _bodyType.text = (r['body_type'] as String?) ?? _bodyType.text;
        _engine.text = (r['engine'] as String?) ?? _engine.text;
        _transmission.text = (r['transmission'] as String?) ?? _transmission.text;
        _year = r['year'] as int? ?? _year;
        _lookupInfo = 'Updated from registry lookup';
      });
    } catch (e) {
      setState(() => _lookupInfo = 'Lookup failed: $e');
    } finally {
      setState(() => _lookingUp = false);
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      await api.patch('/vehicles/${widget.vehicle.id}', {
        'nickname': _nickname.text,
        'rego': _rego.text.isEmpty ? null : _rego.text,
        'vin': _vin.text.isEmpty ? null : _vin.text,
        'make': _make.text.isEmpty ? null : _make.text,
        'model': _model.text.isEmpty ? null : _model.text,
        'colour': _colour.text.isEmpty ? null : _colour.text,
        'body_type': _bodyType.text.isEmpty ? null : _bodyType.text,
        'year': _year,
        'engine': _engine.text.isEmpty ? null : _engine.text,
        'transmission': _transmission.text.isEmpty ? null : _transmission.text,
        'odometer_km': int.tryParse(_odometer.text),
        'is_primary': _isPrimary,
        'vehicle_type': _vehicleType,
        'club_reg': _clubReg,
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
      appBar: AppBar(title: const Text('Edit vehicle')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _nickname,
                decoration: const InputDecoration(labelText: 'Nickname'),
                validator: (v) => v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _vehicleType,
                decoration: const InputDecoration(labelText: 'Vehicle type'),
                items: const [
                  DropdownMenuItem(value: 'car', child: Text('Car')),
                  DropdownMenuItem(value: 'motorcycle', child: Text('Motorcycle')),
                ],
                onChanged: (v) => setState(() => _vehicleType = v ?? 'car'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _rego,
                      decoration: const InputDecoration(labelText: 'Rego'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 110,
                    child: DropdownButtonFormField<String>(
                      value: _state,
                      decoration: const InputDecoration(labelText: 'State'),
                      items: const [
                        DropdownMenuItem(value: 'NSW', child: Text('NSW')),
                        DropdownMenuItem(value: 'VIC', child: Text('VIC')),
                        DropdownMenuItem(value: 'QLD', child: Text('QLD')),
                        DropdownMenuItem(value: 'WA', child: Text('WA')),
                        DropdownMenuItem(value: 'SA', child: Text('SA')),
                        DropdownMenuItem(value: 'TAS', child: Text('TAS')),
                        DropdownMenuItem(value: 'NT', child: Text('NT')),
                        DropdownMenuItem(value: 'ACT', child: Text('ACT')),
                      ],
                      onChanged: (v) => setState(() => _state = v ?? 'VIC'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.tonalIcon(
                    onPressed: _lookingUp ? null : _lookup,
                    icon: _lookingUp
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.search),
                    label: const Text('Lookup'),
                  ),
                ],
              ),
              if (_lookupInfo != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_lookupInfo!,
                      style:
                          TextStyle(color: Theme.of(context).colorScheme.primary)),
                ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _vin,
                decoration: const InputDecoration(labelText: 'VIN'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _make,
                      decoration: const InputDecoration(labelText: 'Make'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _model,
                      decoration: const InputDecoration(labelText: 'Model'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      value: _year,
                      decoration: const InputDecoration(labelText: 'Year'),
                      items: [
                        for (var y = DateTime.now().year + 1; y >= 1980; y--)
                          DropdownMenuItem(value: y, child: Text('$y')),
                      ],
                      onChanged: (v) => setState(() => _year = v),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextFormField(
                      controller: _odometer,
                      decoration: const InputDecoration(
                        labelText: 'Odometer (km)',
                      ),
                      keyboardType: TextInputType.number,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _engine,
                decoration: const InputDecoration(labelText: 'Engine'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _transmission,
                decoration: const InputDecoration(labelText: 'Transmission'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _colour,
                decoration: const InputDecoration(labelText: 'Colour'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _bodyType,
                decoration: const InputDecoration(labelText: 'Body type'),
              ),
              const SizedBox(height: 12),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Set as primary vehicle'),
                value: _isPrimary,
                onChanged: (v) => setState(() => _isPrimary = v ?? false),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Club registration'),
                subtitle: const Text(
                    'Club-registered vehicles are not used for ATO logbook '
                    'claims, so the logbook feature is disabled.'),
                value: _clubReg,
                onChanged: (v) => setState(() => _clubReg = v ?? false),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: const Text('Save changes'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
