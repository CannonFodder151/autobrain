import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class ServicePredictionScreen extends StatefulWidget {
  const ServicePredictionScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ServicePredictionScreen> createState() => _ServicePredictionScreenState();
}

class _ServicePredictionScreenState extends State<ServicePredictionScreen> {
  ServicePrediction? _result;
  bool _loading = false;
  String? _error;
  String _type = 'oil_change';
  final _odo = TextEditingController();
  final _lastKm = TextEditingController();

  @override
  void dispose() {
    _odo.dispose();
    _lastKm.dispose();
    super.dispose();
  }

  Future<void> _predict(Vehicle v) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = context.read<AuthState>().api;
      final data = await api.post(
              '/vehicles/${widget.vehicleId}/services/predict', {
            'make': v.make ?? '',
            'model': v.model ?? '',
            'year': v.year ?? DateTime.now().year,
            'odometer_km': int.tryParse(_odo.text) ?? (v.odometerKm ?? 0),
            'last_service_km': int.tryParse(_lastKm.text),
            'service_type': _type,
          }) as Map<String, dynamic>;
      setState(() => _result = ServicePrediction.fromJson(data));
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _schedule(ServicePrediction p) async {
    try {
      final api = context.read<AuthState>().api;
      await api.post('/vehicles/${widget.vehicleId}/services', {
        'service_date': p.nextDueDate,
        'odometer_km': p.nextDueKm,
        'service_type': p.serviceType,
        'cost': 0.0,
        'status': 'scheduled',
        'description': p.reason,
        'steps': const [],
        'items': const [],
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Added to Upcoming services')),
        );
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI service prediction')),
      body: FutureBuilder(
        future: context
            .read<AuthState>()
            .api
            .get('/vehicles/${widget.vehicleId}'),
        builder: (context, snap) {
          final Vehicle? vehicle = snap.hasData
              ? Vehicle.fromJson(snap.data as Map<String, dynamic>)
              : null;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (vehicle == null)
                const Text('Add a vehicle first.')
              else ...[
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.directions_car),
                    title: Text(vehicle.displayName),
                    subtitle: Text(
                        'Current odo: ${vehicle.odometerKm ?? 'unknown'} km'),
                  ),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: _type,
                  items: const [
                    DropdownMenuItem(
                        value: 'oil_change', child: Text('Oil change')),
                    DropdownMenuItem(
                        value: 'brake_pads', child: Text('Brake pads')),
                    DropdownMenuItem(
                        value: 'air_filter', child: Text('Air filter')),
                    DropdownMenuItem(
                        value: 'spark_plugs', child: Text('Spark plugs')),
                    DropdownMenuItem(
                        value: 'timing_belt', child: Text('Timing belt')),
                    DropdownMenuItem(
                        value: 'scheduled', child: Text('Scheduled service')),
                  ],
                  onChanged: (v) => setState(() => _type = v ?? 'oil_change'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _odo,
                  decoration: const InputDecoration(
                    labelText: 'Current odometer (km)',
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _lastKm,
                  decoration: const InputDecoration(
                    labelText: 'Last service odometer (km, optional)',
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _loading ? null : () => _predict(vehicle),
                  icon: const Icon(Icons.smart_toy),
                  label: const Text('Predict next service'),
                ),
                if (_loading) const Padding(
                  padding: EdgeInsets.all(16),
                  child: Center(child: CircularProgressIndicator()),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(_error!,
                        style: TextStyle(color: Colors.red.shade700)),
                  ),
                if (_result != null) ...[
                  const SizedBox(height: 20),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Next: ${_result!.serviceType}',
                              style: Theme.of(context).textTheme.titleLarge),
                          const SizedBox(height: 8),
                          _Row(
                              'Due in',
                              '${_result!.dueInKm} km'),
                          _Row('Next date',
                              _result!.nextDueDate),
                          _Row('Interval',
                              '${_result!.intervalKm} km'),
                          _Row('Confidence',
                              '${(_result!.confidence * 100).toStringAsFixed(0)}%'),
                          const Divider(),
                          Text(_result!.reason,
                              style: Theme.of(context).textTheme.bodySmall),
                          const SizedBox(height: 12),
                          FilledButton.tonalIcon(
                            onPressed: () => _schedule(_result!),
                            icon: const Icon(Icons.schedule, size: 18),
                            label: const Text('Add as scheduled service'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ],
          );
        },
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(flex: 2, child: Text(label, softWrap: true)),
            const SizedBox(width: 12),
            Expanded(
              flex: 3,
              child: Text(value,
                  softWrap: true,
                  textAlign: TextAlign.end,
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      );
}
