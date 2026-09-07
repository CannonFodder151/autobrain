import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/fuel_types.dart';
import '../../widgets/responsive.dart';

class AddVehicleScreen extends StatefulWidget {
  const AddVehicleScreen({super.key});

  @override
  State<AddVehicleScreen> createState() => _AddVehicleScreenState();
}

class _AddVehicleScreenState extends State<AddVehicleScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nickname = TextEditingController();
  final _rego = TextEditingController();
  final _vin = TextEditingController();
  final _make = TextEditingController();
  final _model = TextEditingController();
  final _colour = TextEditingController();
  final _bodyType = TextEditingController();
  final _engine = TextEditingController();
  final _transmission = TextEditingController();
  final _odometer = TextEditingController();
  int? _year;
  String _state = 'VIC';
  String _vehicleType = 'car';
  bool _busy = false;
  bool _isPrimary = false;
  bool _clubReg = false;
  bool _lookingUp = false;
  String? _lookupInfo;
  String? _fuelType;
  List<String> _fuelTypes = defaultFuelTypes;
  int? _maxVehicles;
  int? _vehicleCount;

  @override
  void initState() {
    super.initState();
    _loadQuota();
    _loadFuelTypes();
  }

  Future<void> _loadFuelTypes() async {
    try {
      final api = context.read<AuthState>().api;
      final types = await fetchFuelTypes(api);
      if (mounted) {
        setState(() {
          _fuelTypes = types;
          if (_fuelType != null && !_fuelTypes.contains(_fuelType)) {
            _fuelTypes = [_fuelType!, ..._fuelTypes];
          }
        });
      }
    } catch (_) {
      // Keep the static fallback list already in _fuelTypes.
    }
  }

  Future<void> _loadQuota() async {
    try {
      final api = context.read<AuthState>().api;
      final me = await api.get('/auth/me') as Map<String, dynamic>;
      setState(() {
        _maxVehicles = me['max_vehicles'] as int?;
        _vehicleCount = me['vehicle_count'] as int?;
      });
    } catch (_) {}
  }

  int get _remaining =>
      (_maxVehicles ?? 0) - (_vehicleCount ?? 0);

  bool get _atLimit =>
      _maxVehicles != null && _vehicleCount != null && _remaining <= 0;

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
        _vin.text = (r['vin'] as String?) ?? '';
        _make.text = (r['make'] as String?) ?? '';
        _model.text = (r['model'] as String?) ?? '';
        _colour.text = (r['colour'] as String?) ?? '';
        _bodyType.text = (r['body_type'] as String?) ?? '';
        _engine.text = (r['engine'] as String?) ?? '';
        _transmission.text = (r['transmission'] as String?) ?? '';
        _year = r['year'] as int?;
        final src = (r['source'] as String?) ?? 'unknown';
        final matched = (r['matched'] as String?) ?? '';
        final desc = (r['description'] as String?) ?? '';
        _lookupInfo =
            '${src == 'provider' ? 'Live registry data' : 'Best guess ($src)'}'
            '${desc.isEmpty ? '' : ' · $desc'}'
            '${matched.isEmpty ? '' : ' · $matched'}';
      });
    } catch (e) {
      setState(() => _lookupInfo = 'Lookup failed: $e');
    } finally {
      setState(() => _lookingUp = false);
    }
  }

  Future<void> _submit() async {
    if (_atLimit) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Vehicle limit reached — no slots left on this account.')));
      }
      return;
    }
    if (!_formKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      final api = context.read<AuthState>().api;
      await api.post('/vehicles', {
        'nickname': _nickname.text,
        'rego': _rego.text.isEmpty ? null : _rego.text,
        'rego_state': _state,
        'vin': _vin.text.isEmpty ? null : _vin.text,
        'make': _make.text.isEmpty ? null : _make.text,
        'model': _model.text.isEmpty ? null : _model.text,
        'colour': _colour.text.isEmpty ? null : _colour.text,
        'body_type': _bodyType.text.isEmpty ? null : _bodyType.text,
        'year': _year,
        'engine': _engine.text.isEmpty ? null : _engine.text,
        'transmission': _transmission.text.isEmpty ? null : _transmission.text,
        'odometer_km': int.tryParse(_odometer.text) ?? 0,
        'condition': 'good',
        'vehicle_type': _vehicleType,
        'is_primary': _isPrimary,
        'club_reg': _clubReg,
        'fuel_type': _fuelType,
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
      appBar: AppBar(title: const Text('Add vehicle')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
              if (_maxVehicles != null)
                Card(
                  color: _atLimit
                      ? Theme.of(context).colorScheme.errorContainer
                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Icon(
                          _atLimit
                              ? Icons.block
                              : Icons.directions_car,
                          color: _atLimit
                              ? Theme.of(context).colorScheme.error
                              : Theme.of(context).colorScheme.primary,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            _atLimit
                                ? 'No vehicle slots left (limit $_maxVehicles). '
                                    'Ask an administrator to raise your limit.'
                                : '$_remaining of $_maxVehicles vehicle '
                                    'slot${_remaining == 1 ? '' : 's'} remaining',
                            style: TextStyle(
                                fontWeight: FontWeight.w600,
                                color: _atLimit
                                    ? Theme.of(context).colorScheme.error
                                    : null),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 12),
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
                  child: Text(_lookupInfo!, style: TextStyle(
                      color: Theme.of(context).colorScheme.primary)),
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
                        for (var y = DateTime.now().year + 1;
                            y >= 1980;
                            y--)
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
              DropdownButtonFormField<String>(
                value: _fuelType != null && _fuelTypes.contains(_fuelType) ? _fuelType : null,
                decoration: const InputDecoration(
                  labelText: 'Fuel type',
                  hintText: 'Used to pick the default price on map/list',
                ),
                items: [
                  for (final t in _fuelTypes)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (v) => setState(() => _fuelType = v),
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
                    'Victoria requires a physical paper logbook for '
                    'club-registered vehicles, so the digital logbook is disabled.'),
                value: _clubReg,
                onChanged: (v) => setState(() => _clubReg = v ?? false),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy || _atLimit ? null : _submit,
                child: const Text('Save vehicle'),
              ),
            ],
          ),
          ),
        ),
      ),
    );
  }
}
