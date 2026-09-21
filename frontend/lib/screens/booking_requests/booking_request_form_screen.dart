import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../widgets/responsive.dart';

/// Owner submits a booking request to a specific engineer for a vehicle.
class BookingRequestFormScreen extends StatefulWidget {
  const BookingRequestFormScreen({
    super.key,
    this.vehicleId,
    this.engineerId,
  });
  final String? vehicleId;
  final String? engineerId;

  @override
  State<BookingRequestFormScreen> createState() => _BookingRequestFormScreenState();
}

class _BookingRequestFormScreenState extends State<BookingRequestFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _description = TextEditingController();
  final _odometer = TextEditingController();
  final _symptoms = TextEditingController();
  final _mods = TextEditingController();
  bool _busy = false;

  List<Vehicle> _vehicles = [];
  List<Map<String, dynamic>> _engineers = [];
  Vehicle? _selectedVehicle;
  String? _selectedEngineerId;
  String _serviceType = 'repair';
  String _urgency = 'normal';
  DateTime? _preferredDate;
  TimeOfDay? _preferredTime;
  bool _autoGeneratePrecheck = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    // Load vehicles
    try {
      final data = await api.get('/vehicles') as List;
      _vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      if (widget.vehicleId != null) {
        _selectedVehicle = Vehicle.byId(_vehicles, widget.vehicleId!);
      }
    } catch (_) {}

    // Load engineers
    try {
      final data = await api.get('/engineers/search?is_active=true&sort=rating&order=desc') as Map<String, dynamic>;
      final results = data['results'] as List? ?? [];
      _engineers = results.cast<Map<String, dynamic>>();
      if (widget.engineerId != null) {
        _selectedEngineerId = widget.engineerId!;
      }
    } catch (_) {}

    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _description.dispose();
    _odometer.dispose();
    _symptoms.dispose();
    _mods.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_selectedVehicle == null || _selectedEngineerId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select a vehicle and an engineer')),
      );
      return;
    }
    setState(() => _busy = true);
    final api = context.read<AuthState>().api;
    final body = {
      'service_type': _serviceType,
      'description': _description.text.isEmpty ? null : _description.text,
      'preferred_date': _preferredDate != null
          ? '${_preferredDate!.year}-${_preferredDate!.month.toString().padLeft(2, '0')}-${_preferredDate!.day.toString().padLeft(2, '0')}'
          : null,
      'preferred_time': _preferredTime != null
          ? '${_preferredTime!.hour.toString().padLeft(2, '0')}:${_preferredTime!.minute.toString().padLeft(2, '0')}'
          : null,
      'urgency': _urgency,
      'symptoms': _symptoms.text.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList(),
      'odometer_km': int.tryParse(_odometer.text),
      'mods': _mods.text.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList(),
      'auto_generate_precheck': _autoGeneratePrecheck,
    };
    try {
      await api.post(
        '/vehicles/${_selectedVehicle!.id}/engineers/$_selectedEngineerId/requests',
        body,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Booking request submitted')),
        );
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to submit: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Book an Engineer')),
      body: _busy
          ? const Center(child: CircularProgressIndicator())
          : Form(
              key: _formKey,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  // Vehicle selector
                  _sectionTitle(theme, 'Vehicle'),
                  DropdownButtonFormField<String>(
                    value: _selectedVehicle?.id,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    ),
                    items: _vehicles
                        .map((v) => DropdownMenuItem(
                              value: v.id,
                              child: Text(v.displayName),
                            ))
                        .toList(),
                    onChanged: (id) {
                      setState(() {
                        _selectedVehicle = _vehicles.firstWhere((v) => v.id == id);
                      });
                    },
                    validator: (v) => v == null ? 'Select a vehicle' : null,
                  ),
                  const SizedBox(height: 20),

                  // Engineer selector
                  _sectionTitle(theme, 'Engineer'),
                  DropdownButtonFormField<String>(
                    value: _selectedEngineerId,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    ),
                    items: _engineers
                        .map((e) => DropdownMenuItem(
                              value: e['id'] as String,
                              child: Text(
                                '${e['display_name'] ?? 'Unknown'} (${e['rating']?.toStringAsFixed(1) ?? '0.0'} stars)',
                              ),
                            ))
                        .toList(),
                    onChanged: (id) {
                      setState(() => _selectedEngineerId = id);
                    },
                    validator: (v) => v == null ? 'Select an engineer' : null,
                  ),
                  const SizedBox(height: 20),

                  // Service type
                  _sectionTitle(theme, 'Service Type'),
                  DropdownButtonFormField<String>(
                    value: _serviceType,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'repair', child: Text('Repair')),
                      DropdownMenuItem(value: 'diagnostic', child: Text('Diagnostic')),
                      DropdownMenuItem(value: 'tire', child: Text('Tire')),
                      DropdownMenuItem(value: 'scheduled', child: Text('Scheduled Service')),
                      DropdownMenuItem(value: 'custom', child: Text('Custom')),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _serviceType = v);
                    },
                  ),
                  const SizedBox(height: 20),

                  // Description
                  TextFormField(
                    controller: _description,
                    decoration: const InputDecoration(
                      labelText: 'Description',
                      border: OutlineInputBorder(),
                      alignLabelWithHint: true,
                    ),
                    maxLines: 3,
                    maxLength: 2000,
                  ),
                  const SizedBox(height: 20),

                  // Urgency
                  _sectionTitle(theme, 'Urgency'),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(value: 'low', label: Text('Low')),
                      ButtonSegment(value: 'normal', label: Text('Normal')),
                      ButtonSegment(value: 'high', label: Text('High')),
                      ButtonSegment(value: 'urgent', label: Text('Urgent')),
                    ],
                    selected: {_urgency},
                    onSelectionChanged: (s) {
                      setState(() => _urgency = s.first);
                    },
                  ),
                  const SizedBox(height: 20),

                  // Preferred date
                  _sectionTitle(theme, 'Preferred Date'),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.calendar_today),
                    title: Text(
                      _preferredDate != null
                          ? '${_preferredDate!.day}/${_preferredDate!.month}/${_preferredDate!.year}'
                          : 'Select a date',
                    ),
                    onTap: () async {
                      final date = await showDatePicker(
                        context: context,
                        initialDate: _preferredDate ?? DateTime.now(),
                        firstDate: DateTime.now(),
                        lastDate: DateTime.now().add(const Duration(days: 90)),
                      );
                      if (date != null) setState(() => _preferredDate = date);
                    },
                  ),
                  const SizedBox(height: 8),

                  // Preferred time
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.access_time),
                    title: Text(
                      _preferredTime != null
                          ? '${_preferredTime!.hour.toString().padLeft(2, '0')}:${_preferredTime!.minute.toString().padLeft(2, '0')}'
                          : 'Select a time',
                    ),
                    onTap: () async {
                      final time = await showTimePicker(
                        context: context,
                        initialTime: _preferredTime ?? const TimeOfDay(hour: 9, minute: 0),
                      );
                      if (time != null) setState(() => _preferredTime = time);
                    },
                  ),
                  const SizedBox(height: 20),

                  // Odometer
                  TextFormField(
                    controller: _odometer,
                    decoration: const InputDecoration(
                      labelText: 'Odometer (km)',
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                  ),
                  const SizedBox(height: 20),

                  // Symptoms
                  TextFormField(
                    controller: _symptoms,
                    decoration: const InputDecoration(
                      labelText: 'Symptoms (comma-separated)',
                      hintText: 'e.g. Engine noise, vibration, warning light',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Modifications
                  TextFormField(
                    controller: _mods,
                    decoration: const InputDecoration(
                      labelText: 'Modifications (comma-separated)',
                      hintText: 'e.g. ECU tune, upgraded exhaust, lowered suspension',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Auto-generate pre-check
                  SwitchListTile(
                    title: const Text('Generate pre-check report'),
                    subtitle: const Text(
                      'Automatically create a pre-check report based on vehicle data and modifications',
                      style: TextStyle(fontSize: 12),
                    ),
                    value: _autoGeneratePrecheck,
                    onChanged: (v) => setState(() => _autoGeneratePrecheck = v),
                  ),
                  const SizedBox(height: 24),

                  // Submit button
                  SizedBox(
                    height: 48,
                    child: ElevatedButton(
                      onPressed: _submit,
                      child: const Text('Submit Booking Request'),
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _sectionTitle(ThemeData theme, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
      ),
    );
  }
}