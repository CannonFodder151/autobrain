import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass_api.dart';

/// Vehicle selector + VIN scan input for the VASS pre-check wizard.
class VassVehicleSelectorScreen extends StatefulWidget {
  const VassVehicleSelectorScreen({super.key});

  @override
  State<VassVehicleSelectorScreen> createState() =>
      _VassVehicleSelectorScreenState();
}

class _VassVehicleSelectorScreenState
    extends State<VassVehicleSelectorScreen> {
  late final VassApi _api;
  final TextEditingController _vinController = TextEditingController();

  List<String> _makes = const [];
  String? _make;
  List<String> _models = const [];
  String? _model;
  int? _year;
  int? _yearFrom;
  int? _yearTo;
  bool _loadingMakes = true;
  bool _loadingModels = false;
  String? _error;
  VinValidationResponse? _vinValidation;

  @override
  void initState() {
    super.initState();
    _api = VassApi(context.read<AuthState>().api);
    _loadMakes();
  }

  Future<void> _loadMakes() async {
    setState(() => _loadingMakes = true);
    try {
      final makes = await _api.listVehicleMakes();
      if (!mounted) return;
      setState(() {
        _makes = makes;
        _loadingMakes = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException ? e.message : '$e';
        _loadingMakes = false;
      });
    }
  }

  Future<void> _onMakeChanged(String? make) async {
    setState(() {
      _make = make;
      _model = null;
      _models = const [];
      _year = null;
      _yearFrom = null;
      _yearTo = null;
    });
    if (make == null) return;
    setState(() => _loadingModels = true);
    try {
      final models = await _api.listVehicleModels(make);
      if (!mounted) return;
      setState(() {
        _models = models;
        _loadingModels = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException ? e.message : '$e';
        _loadingModels = false;
      });
    }
  }

  Future<void> _onModelChanged(String? model) async {
    setState(() {
      _model = model;
      _year = null;
      _yearFrom = null;
      _yearTo = null;
    });
    if (_make == null || model == null) return;
    try {
      final range = await _api.getVehicleYearRange(_make!, model);
      if (!mounted) return;
      setState(() {
        _yearFrom = range['year_from'] as int?;
        _yearTo = range['year_to'] as int?;
        final years = range['years'] as List?;
        if (years != null && years.isNotEmpty) {
          _year = years.first as int;
        } else if (_yearFrom != null) {
          _year = _yearFrom;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e is ApiException ? e.message : '$e');
    }
  }

  Future<void> _validateVin() async {
    final vin = _vinController.text.trim().toUpperCase();
    if (vin.length != 17) {
      setState(() => _vinValidation = null);
      return;
    }
    try {
      final res = await _api.validateVin(vin);
      if (!mounted) return;
      setState(() => _vinValidation = res);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e is ApiException ? e.message : '$e');
    }
  }

  @override
  void dispose() {
    _vinController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final years = (_yearFrom != null && _yearTo != null)
        ? List<int>.generate(
            _yearTo! - _yearFrom! + 1, (i) => _yearFrom! + i)
        : const <int>[];
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicle Selector')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_error!,
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.error)),
              ),
            _loadingMakes
                ? const Center(child: CircularProgressIndicator())
                : DropdownButtonFormField<String>(
                    initialValue: _make,
                    decoration: const InputDecoration(labelText: 'Make'),
                    items: _makes
                        .map((m) =>
                            DropdownMenuItem(value: m, child: Text(m)))
                        .toList(),
                    onChanged: _onMakeChanged,
                  ),
            const SizedBox(height: 12),
            _loadingModels
                ? const Center(child: CircularProgressIndicator())
                : DropdownButtonFormField<String>(
                    initialValue: _model,
                    decoration: const InputDecoration(labelText: 'Model'),
                    items: _models
                        .map((m) =>
                            DropdownMenuItem(value: m, child: Text(m)))
                        .toList(),
                    onChanged: _onModelChanged,
                  ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              initialValue: _year,
              decoration: const InputDecoration(labelText: 'Year'),
              items: years
                  .map((y) =>
                      DropdownMenuItem(value: y, child: Text('$y')))
                  .toList(),
              onChanged: (y) => setState(() => _year = y),
            ),
            const SizedBox(height: 24),
            const Text('Or scan / enter VIN',
                style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            TextField(
              controller: _vinController,
              textCapitalization: TextCapitalization.characters,
              maxLength: 17,
              decoration: const InputDecoration(
                labelText: 'VIN (17 chars)',
                suffixIcon: Icon(Icons.qr_code_scanner),
              ),
              onChanged: (_) => _validateVin(),
            ),
            if (_vinValidation != null) ...[
              const SizedBox(height: 8),
              Text(
                _vinValidation!.isValid
                    ? 'VIN valid${_vinValidation!.manufacturer != null ? ' — ${_vinValidation!.manufacturer}' : ''}'
                    : 'VIN invalid: ${_vinValidation!.errors.join(', ')}',
                style: TextStyle(
                  color: _vinValidation!.isValid
                      ? Colors.green
                      : Theme.of(context).colorScheme.error,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
