import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/models.dart';
import 'add_fuel_screen.dart';

class FuelScreen extends StatefulWidget {
  const FuelScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<FuelScreen> createState() => _FuelScreenState();
}

class _FuelScreenState extends State<FuelScreen> {
  List<FuelLog> _logs = const [];
  bool _loading = true;
  int? _fy; // null = all time; otherwise Australian FY (e.g. 2026)

  int get _currentFy {
    final now = DateTime.now();
    return now.month >= 7 ? now.year + 1 : now.year;
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api.get(
              '/vehicles/${widget.vehicleId}/fuel'
          '${_fy != null ? '?fy=$_fy' : ''}') as List;
      _logs = data
          .map((e) => FuelLog.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  List<FlSpot> _efficiencySpots() {
    final eff = _logs.where((l) => l.lPer100km != null).toList();
    return [
      for (var i = 0; i < eff.length; i++)
        FlSpot(i.toDouble(), eff[i].lPer100km!),
    ];
  }

  Future<void> _openAdd({FuelLog? existing}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AddFuelScreen(
          vehicleId: widget.vehicleId,
          existing: existing,
        ),
      ),
    );
    _load();
  }

  Future<void> _delete(FuelLog l) async {
    final api = context.read<AuthState>().api;
    try {
      await api.delete('/vehicles/${widget.vehicleId}/fuel/${l.id}');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _export(bool withImages) async {
    final api = context.read<AuthState>().api;
    final fy = _fy ?? _currentFy;
    try {
      final bytes = await api.export(
          '/vehicles/${widget.vehicleId}/fuel/export?fy=$fy'
          '${withImages ? '&fmt=zip' : ''}');
      final name = 'fuel-FY$fy${withImages ? '-with-images.zip' : '.csv'}';
      await downloadBytes(name, bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Export failed: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final spots = _efficiencySpots();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Fuel tracker'),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Export',
            icon: const Icon(Icons.download_outlined),
            onSelected: (v) => _export(v == 'zip'),
            itemBuilder: (_) => [
              const PopupMenuItem(
                  value: 'csv', child: Text('Export CSV')),
              const PopupMenuItem(
                  value: 'zip', child: Text('Export CSV + receipts (ZIP)')),
            ],
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openAdd(),
        icon: const Icon(Icons.add),
        label: const Text('Add fill-up'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _SummaryCard(logs: _logs),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    children: [
                      ChoiceChip(
                        label: const Text('All'),
                        selected: _fy == null,
                        onSelected: (_) {
                          setState(() => _fy = null);
                          _load();
                        },
                      ),
                      for (final fy in [_currentFy, _currentFy - 1, _currentFy - 2])
                        ChoiceChip(
                          label: Text('FY${fy - 1}/${fy % 100}'),
                          selected: _fy == fy,
                          onSelected: (_) {
                            setState(() => _fy = fy);
                            _load();
                          },
                        ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  if (spots.length >= 2) ...[
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Efficiency (L/100km)',
                                style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 12),
                            SizedBox(
                              height: 180,
                              child: LineChart(
                                LineChartData(
                                  gridData: const FlGridData(show: false),
                                  titlesData: const FlTitlesData(
                                    leftTitles: AxisTitles(),
                                    bottomTitles: AxisTitles(),
                                  ),
                                  borderData: FlBorderData(show: true),
                                  lineBarsData: [
                                    LineChartBarData(
                                      spots: spots,
                                      isCurved: true,
                                      color: Theme.of(context)
                                          .colorScheme
                                          .primary,
                                      barWidth: 3,
                                      dotData: const FlDotData(show: true),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  Text('History', style: Theme.of(context).textTheme.titleMedium),
                  for (final l in _logs)
                    Card(
                      child: ListTile(
                        title: Text(
                            '${l.fillDate} · ${l.litres.toStringAsFixed(1)} L'),
                        subtitle: Text(
                          '${l.odometerKm} km'
                          '${l.lPer100km != null ? ' · ${l.lPer100km!.toStringAsFixed(1)} L/100km' : ''}'
                          '${l.costPerKm != null ? ' · \$${l.costPerKm!.toStringAsFixed(2)}/km' : ''}'
                          '${l.notes != null ? ' · ${l.notes}' : ''}',
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (l.receiptId != null)
                              const Padding(
                                padding: EdgeInsets.only(right: 6),
                                child: Icon(Icons.receipt_long,
                                    size: 18, color: Colors.grey),
                              ),
                            Text('\$${l.totalCost.toStringAsFixed(2)}'),
                            PopupMenuButton<String>(
                              onSelected: (v) {
                                if (v == 'edit') _openAdd(existing: l);
                                if (v == 'delete') _delete(l);
                              },
                              itemBuilder: (_) => const [
                                PopupMenuItem(value: 'edit', child: Text('Edit')),
                                PopupMenuItem(
                                    value: 'delete', child: Text('Delete')),
                              ],
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

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.logs});
  final List<FuelLog> logs;

  @override
  Widget build(BuildContext context) {
    final eff = logs.where((l) => l.lPer100km != null).toList();
    final costK = logs.where((l) => l.costPerKm != null).toList();
    final litres = logs.fold<double>(0, (a, b) => a + b.litres);
    final total = logs.fold<double>(0, (a, b) => a + b.totalCost);
    final avgEff = eff.isEmpty
        ? null
        : eff.map((l) => l.lPer100km!).reduce((a, b) => a + b) / eff.length;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _v(context, 'L total', litres.toStringAsFixed(0)),
            _v(context, 'Avg L/100km',
                avgEff?.toStringAsFixed(1) ?? '—'),
            _v(context, 'Cost/km',
                costK.isEmpty ? '—' : '\$${(costK.map((l) => l.costPerKm!).reduce((a, b) => a + b) / costK.length).toStringAsFixed(2)}'),
            _v(context, 'Total', '\$${total.toStringAsFixed(0)}'),
          ],
        ),
      ),
    );
  }

  Widget _v(BuildContext context, String label, String value) => Column(
        children: [
          Text(value, style: Theme.of(context).textTheme.titleMedium),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      );
}
