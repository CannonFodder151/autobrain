import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../community_garage/widgets/premium_gate.dart';
import '../../core/api_client.dart';
import '../../core/auth_state.dart';

/// Premium-only Rego Lookup tool (AUT-2416). A user types an Australian plate
/// + state and the backend hits the rego-lookup-api, returning VIN + details
/// + rego status/expiry. The whole screen is premium-gated; non-premium sees
/// the upgrade prompt instead.
class RegoLookupScreen extends StatefulWidget {
  const RegoLookupScreen({super.key});

  @override
  State<RegoLookupScreen> createState() => _RegoLookupScreenState();
}

class _RegoLookupScreenState extends State<RegoLookupScreen> {
  final _plateCtrl = TextEditingController();
  String _state = 'VIC';
  String _vehicleType = 'car';
  Map<String, dynamic>? _result;
  bool _loading = false;
  String? _error;

  static const _states = [
    'NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'NT', 'ACT',
  ];

  @override
  void dispose() {
    _plateCtrl.dispose();
    super.dispose();
  }

  Future<void> _lookup() async {
    final plate = _plateCtrl.text.trim();
    if (plate.isEmpty) {
      setState(() => _error = 'Enter a registration plate');
      return;
    }
    final api = context.read<AuthState>().api;
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });
    try {
      final data = await api.post('/vehicles/rego-lookup', {
        'rego': plate,
        'state': _state,
        'vehicle_type': _vehicleType,
      }) as Map<String, dynamic>;
      setState(() => _result = data);
    } on ApiException catch (e) {
      if (e.statusCode == 403) {
        setState(() => _error =
            'Rego lookup is a premium feature. Upgrade to enable it.');
      } else if (e.statusCode == 404) {
        setState(() => _error =
            'No registration data found for that plate — check the state.');
      } else {
        setState(() => _error = e.message);
      }
    } catch (e) {
      setState(() => _error = 'Lookup failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!context.watch<AuthState>().premium) {
      return Scaffold(
        appBar: AppBar(title: const Text('Rego Lookup')),
        body: const PremiumGate(
          lockedReason:
              'Rego Lookup is a premium tool. Enter any Australian plate and '
              'pull VIN, vehicle details, and current registration status.',
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Rego Lookup')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Look up an Australian plate',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(
                    'Pull VIN, vehicle details, and current registration '
                    'status from the rego lookup service.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _plateCtrl,
                    textCapitalization: TextCapitalization.characters,
                    inputFormatters: [
                      LengthLimitingTextInputFormatter(8),
                      FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z0-9]')),
                    ],
                    decoration: const InputDecoration(
                      labelText: 'Registration plate',
                      hintText: 'e.g. TCRWN',
                    ),
                    onSubmitted: (_) => _lookup(),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _state,
                          decoration: const InputDecoration(labelText: 'State'),
                          items: _states
                              .map((s) => DropdownMenuItem(
                                    value: s,
                                    child: Text(s),
                                  ))
                              .toList(),
                          onChanged: (v) => setState(() => _state = v ?? 'VIC'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _vehicleType,
                          decoration:
                              const InputDecoration(labelText: 'Vehicle type'),
                          items: const [
                            DropdownMenuItem(value: 'car', child: Text('Car')),
                            DropdownMenuItem(
                                value: 'motorcycle', child: Text('Motorcycle')),
                          ],
                          onChanged: (v) =>
                              setState(() => _vehicleType = v ?? 'car'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: _loading ? null : _lookup,
                    icon: _loading
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.search),
                    label: const Text('Look up'),
                  ),
                ],
              ),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Colors.red.shade600)),
          ],
          if (_result != null) ...[
            const SizedBox(height: 12),
            _ResultCard(result: _result!),
          ],
        ],
      ),
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});
  final Map<String, dynamic> result;

  String? _str(String key) {
    final v = result[key];
    if (v == null) return null;
    final s = v.toString();
    return s.isEmpty ? null : s;
  }

  int? _int(String key) {
    final v = result[key];
    if (v is int) return v;
    if (v is num) return v.toInt();
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final status = (_str('status') ?? 'registered').toLowerCase();
    final valid = {'registered', 'valid', 'current', 'active'}.contains(status);
    final expiry = _str('expiry_date');
    final source = _str('source') ?? 'unknown';

    final rows = <MapEntry<String, String>>[
      MapEntry('Plate', _str('rego') ?? '—'),
      if (_str('vin') != null) MapEntry('VIN', _str('vin')!),
      if (_str('make') != null || _str('model') != null)
        MapEntry('Vehicle',
            '${_str('make') ?? ''} ${_str('model') ?? ''} ${_int('year') != null ? '(${_int('year')})' : ''}'
                .trim()),
      if (_str('body_type') != null) MapEntry('Body', _str('body_type')!),
      if (_str('colour') != null) MapEntry('Colour', _str('colour')!),
      if (_str('engine') != null) MapEntry('Engine', _str('engine')!),
      if (_str('transmission') != null)
        MapEntry('Transmission', _str('transmission')!),
      if (_str('state') != null) MapEntry('State', _str('state')!),
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  valid ? Icons.verified : Icons.error_outline,
                  color: valid ? Colors.green.shade600 : Colors.red.shade600,
                ),
                const SizedBox(width: 8),
                Text(
                  valid ? 'Rego valid' : 'Rego not current',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ],
            ),
            if (expiry != null) ...[
              const SizedBox(height: 4),
              Text('Expires: $expiry',
                  style: TextStyle(color: scheme.onSurfaceVariant)),
            ],
            const SizedBox(height: 14),
            for (final r in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 110,
                      child: Text(r.key,
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontWeight: FontWeight.w600,
                          )),
                    ),
                    Expanded(
                      child: SelectableText(r.value),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 10),
            Text(
              'Source: $source',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}
