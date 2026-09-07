import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/models.dart';
import '../../widgets/stale_hint.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  Analytics? _analytics;
  bool _loading = true;
  bool _stale = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    final path = '/vehicles/${widget.vehicleId}/analytics';
    final cached = await api.getCachedDecoded(path, null);
    if (cached != null) {
      _analytics = Analytics.fromJson(cached as Map<String, dynamic>);
      _stale = true;
      if (!mounted) return;
      setState(() => _loading = false);
    }
    if (!mounted) return;
    if (!ConnectivityService.instance.isOnline) return;
    try {
      final data = await api.get(path) as Map<String, dynamic>;
      _analytics = Analytics.fromJson(data);
      _stale = false;
    } catch (_) {
      if (_analytics == null) _stale = true;
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final a = _analytics;
    return Scaffold(
      appBar: AppBar(title: const Text('Analytics')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading && _analytics == null
            ? const Center(child: CircularProgressIndicator())
            : a == null && _stale
                ? const Center(child: Text('No data yet'))
                : ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      StaleHint(
                        isStale: _stale,
                        isOffline: !ConnectivityService.instance.isOnline,
                      ),
                      Text('Cost of ownership',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: _MetricCard(
                              label: 'Total',
                              value:
                                  '\$${a.summary.totalCostOfOwnership.toStringAsFixed(0)}',
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: _MetricCard(
                              label: 'Per km',
                              value: a.summary.costPerKm != null
                                  ? '\$${a.summary.costPerKm!.toStringAsFixed(2)}'
                                  : '—',
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: _MetricCard(
                              label: 'Fuel',
                              value:
                                  '\$${a.summary.fuelTotal.toStringAsFixed(0)}',
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: _MetricCard(
                              label: 'Service',
                              value:
                                  '\$${a.summary.serviceTotal.toStringAsFixed(0)}',
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: _MetricCard(
                              label: 'Mods',
                              value:
                                  '\$${a.summary.modTotal.toStringAsFixed(0)}',
                            ),
                          ),
                        ],
                      ),
                      if (a.monthly.isNotEmpty) ...[
                        const SizedBox(height: 16),
                        Text('Monthly spend',
                            style: Theme.of(context).textTheme.titleLarge),
                        for (final m in a.monthly)
                          Card(
                            child: ListTile(
                              dense: true,
                              title: Text(m.month),
                              subtitle: Text(
                                'Fuel \$${m.fuel.toStringAsFixed(0)} · '
                                'Service \$${m.service.toStringAsFixed(0)} · '
                                'Mods \$${m.mod.toStringAsFixed(0)}',
                              ),
                            ),
                          ),
                      ],
                      const SizedBox(height: 16),
                      Text('AI insights',
                          style: Theme.of(context).textTheme.titleLarge),
                      Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              for (final insight in a.insights)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Text('• $insight'),
                                ),
                              const Divider(),
                              Text(
                                '12-month forecast: '
                                '\$${a.forecast.next12Months.toStringAsFixed(0)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold),
                              ),
                              Text(
                                '(${a.forecast.basis})',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            children: [
              Text(value, style: Theme.of(context).textTheme.titleMedium),
              Text(label, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      );
}
