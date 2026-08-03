import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class ValuationScreen extends StatefulWidget {
  const ValuationScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ValuationScreen> createState() => _ValuationScreenState();
}

class _ValuationScreenState extends State<ValuationScreen> {
  Valuation? _valuation;
  bool _loading = false;

  Future<void> _estimate() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _loading = true;
      _valuation = null;
    });
    try {
      final data = await api.post(
          '/vehicles/${widget.vehicleId}/valuation', {}) as Map<String, dynamic>;
      setState(() => _valuation = Valuation.fromJson(data));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Resale value')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Text('Estimated value',
                      style: Theme.of(context).textTheme.bodyMedium),
                  const SizedBox(height: 4),
                  Text(
                    _valuation == null
                        ? '—'
                        : '\$${_valuation!.estimatedValue.toStringAsFixed(0)}',
                    style: Theme.of(context).textTheme.displaySmall,
                  ),
                  if (_valuation != null)
                    Text(
                      'Range \$${_valuation!.low.toStringAsFixed(0)} – \$${_valuation!.high.toStringAsFixed(0)}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _loading ? null : _estimate,
                    icon: const Icon(Icons.sell),
                    label: Text(_loading
                        ? 'Estimating…'
                        : 'Estimate value'),
                  ),
                ],
              ),
            ),
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_valuation != null) ...[
            const SizedBox(height: 12),
            _FactorTable(factors: _valuation!.factors),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Recommendations',
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 8),
                    for (final r in _valuation!.recommendations)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Text('• $r'),
                      ),
                  ],
                ),
              ),
            ),
            Text(
              'Model: ${_valuation!.model}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}

class _FactorTable extends StatelessWidget {
  const _FactorTable({required this.factors});
  final Map<String, dynamic> factors;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Value drivers',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              for (final e in factors.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        flex: 2,
                        child: Text(
                          _pretty(e.key),
                          softWrap: true,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 3,
                        child: Text(
                          e.value.toString(),
                          softWrap: true,
                          textAlign: TextAlign.end,
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      );

  String _pretty(String k) =>
      k.replaceAll('_', ' ').split(' ').map((w) =>
          w.isEmpty ? w : w[0].toUpperCase() + w.substring(1)).join(' ');
}
