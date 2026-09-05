import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';
import 'advisor_models.dart';

class AdvisorFinanceScreen extends StatefulWidget {
  const AdvisorFinanceScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AdvisorFinanceScreen> createState() => _AdvisorFinanceScreenState();
}

class _AdvisorFinanceScreenState extends State<AdvisorFinanceScreen> {
  late final AdvisorApi _api;
  AdvisorFinanceData? _plan;
  bool _loading = false;
  String? _error;

  final _downPayment = TextEditingController(text: '10000');
  final _termMonths = TextEditingController(text: '60');
  final _ratePct = TextEditingController(text: '7.5');
  bool _novated = false;

  @override
  void initState() {
    super.initState();
    _api = AdvisorApi(context.read<AuthState>().api);
  }

  @override
  void dispose() {
    _downPayment.dispose();
    _termMonths.dispose();
    _ratePct.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      final req = AdvisorFinanceRequest(
        downPayment: double.tryParse(_downPayment.text) ?? 0.0,
        termMonths: int.tryParse(_termMonths.text) ?? 60,
        ratePct: double.tryParse(_ratePct.text) ?? 7.5,
        novated: _novated,
      );
      final r = await _api.finance(widget.vehicleId, req);
      if (mounted) setState(() => _plan = AdvisorFinanceData.fromJson(r.data));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'Calculation failed.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Finance')),
      body: RefreshIndicator(
        onRefresh: _submit,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _InputCard(
              downPayment: _downPayment,
              termMonths: _termMonths,
              ratePct: _ratePct,
              novated: _novated,
              onNovatedChanged: (v) => setState(() => _novated = v),
              onSubmit: _submit,
              loading: _loading,
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            if (_plan != null) ...[
              const SizedBox(height: 12),
              _PlanCard(plan: _plan!),
            ],
          ],
        ),
      ),
    );
  }
}

class _InputCard extends StatelessWidget {
  const _InputCard({
    required this.downPayment,
    required this.termMonths,
    required this.ratePct,
    required this.novated,
    required this.onNovatedChanged,
    required this.onSubmit,
    required this.loading,
  });
  final TextEditingController downPayment, termMonths, ratePct;
  final bool novated;
  final ValueChanged<bool> onNovatedChanged;
  final VoidCallback onSubmit;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: downPayment,
                    decoration: const InputDecoration(
                      labelText: 'Down payment (AUD)',
                      isDense: true,
                    ),
                    keyboardType: TextInputType.number,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: termMonths,
                    decoration: const InputDecoration(
                      labelText: 'Term (months)',
                      isDense: true,
                    ),
                    keyboardType: TextInputType.number,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              controller: ratePct,
              decoration: const InputDecoration(
                labelText: 'Interest rate (%)',
                isDense: true,
              ),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              dense: true,
              title: const Text('Novated lease (coming soon)'),
              value: novated,
              onChanged: onNovatedChanged,
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: loading ? null : onSubmit,
              icon: loading
                  ? const SizedBox(width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.calculate),
              label: Text(loading ? 'Calculating…' : 'Calculate'),
            ),
          ],
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.plan});
  final AdvisorFinanceData plan;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Finance plan', style: theme.textTheme.titleMedium),
            const SizedBox(height: 4),
            Text('Vehicle price: \$${plan.vehiclePrice.round()}',
                style: theme.textTheme.bodySmall),
            const SizedBox(height: 12),
            ...plan.modes.map((mode) {
              final title = mode['mode'] ?? 'mode';
              final status = mode['status'] as String? ?? 'ok';
              final isComingSoon = status == 'coming_soon';
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Card(
                  color: isComingSoon
                      ? theme.colorScheme.surfaceContainerHighest
                      : null,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              title[0].toUpperCase() + title.substring(1),
                              style: theme.textTheme.titleSmall,
                            ),
                            const Spacer(),
                            if (isComingSoon)
                              Chip(
                                label: const Text('Coming soon'),
                                visualDensity: VisualDensity.compact,
                              ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        ..._renderRows(mode, isComingSoon),
                      ],
                    ),
                  ),
                ),
              );
            }),
            if (plan.note != null) ...[
              const SizedBox(height: 8),
              Text(plan.note!, style: theme.textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _renderRows(Map<String, dynamic> mode, bool skipDetail) {
    final skip = {'mode', 'status', 'amortization', 'note'};
    final rows = <Widget>[];
    for (final e in mode.entries) {
      if (skip.contains(e.key)) continue;
      final val = e.value;
      rows.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(_pretty(e.key)),
            Text(
              val is num
                  ? '\$${(val as num).round()}'
                  : '$val',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ));
    }
    if (!skipDetail && mode['amortization'] != null) {
      rows.add(const SizedBox(height: 8));
      rows.add(Text('Amortization',
          style: const TextStyle(fontWeight: FontWeight.w600)));
      rows.add(Container(
        height: 120,
        decoration: BoxDecoration(
          border: Border.all(color: Colors.grey.shade300),
          borderRadius: BorderRadius.circular(8),
        ),
        child: ListView.builder(
          shrinkWrap: true,
          padding: const EdgeInsets.all(8),
          itemCount: (mode['amortization'] as List).length.clamp(0, 8),
          itemBuilder: (_, i) {
            final row = mode['amortization'][i];
            return Text(
              'P${(row['period'] as int)}: \$${(row['balance_end'] as num).round()}',
              style: const TextStyle(fontSize: 12),
            );
          },
        ),
      ));
    }
    return rows;
  }

  String _pretty(String k) => k
      .replaceAll('_', ' ')
      .split(' ')
      .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
      .join(' ');
}
