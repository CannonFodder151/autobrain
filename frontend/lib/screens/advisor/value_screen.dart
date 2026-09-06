import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';
import 'advisor_models.dart';

class AdvisorValueScreen extends StatefulWidget {
  const AdvisorValueScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AdvisorValueScreen> createState() => _AdvisorValueScreenState();
}

class _AdvisorValueScreenState extends State<AdvisorValueScreen> {
  late final AdvisorApi _advisorApi;
  AdvisorResponse? _resp;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _advisorApi = AdvisorApi(context.read<AuthState>().api);
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final r = await _advisorApi.value(widget.vehicleId);
      if (mounted) setState(() => _resp = r);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'Failed to load value data.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicle Value')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!))
                : _resp == null
                    ? const Center(child: Text('No data available.'))
                    : _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    final data = _resp!.data;
    final valueData = AdvisorValueData.fromJson(data);
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (valueData.note != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(valueData.note!,
                style: theme.textTheme.bodySmall),
          ),
        _ValueCard(data: valueData),
        const SizedBox(height: 12),
        _TradeInCard(tradeIn: valueData.tradeIn),
        if (valueData.comparables.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('Comparables',
              style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ...valueData.comparables.map((c) => ListTile(
                dense: true,
                leading: const Icon(Icons.compare_arrows, size: 20),
                title: Text(c.title,
                    maxLines: 1, overflow: TextOverflow.ellipsis),
                trailing: Text(
                    '\$${c.price.round()}',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
              )),
        ],
        if (valueData.stale)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text('Cached data (24h)',
                style: theme.textTheme.bodySmall),
          ),
        Text('Model: ${_resp!.model}',
            style: theme.textTheme.bodySmall),
      ],
    );
  }
}

class _ValueCard extends StatelessWidget {
  const _ValueCard({required this.data});
  final AdvisorValueData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text('Estimated market value',
                style: theme.textTheme.bodyMedium),
            const SizedBox(height: 8),
            Text(
              data.mid == null
                  ? '—'
                  : '\$${data.mid!.round()}',
              style: theme.textTheme.displaySmall,
            ),
            if (data.low != null && data.high != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '\$${data.low!.round()} – \$${data.high!.round()}',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: _Stat(label: 'Condition', value: '×${data.conditionMultiplier.toStringAsFixed(2)}')),
                const SizedBox(width: 12),
                Expanded(child: _Stat(label: 'Km adj.', value: '×${data.kmMultiplier.toStringAsFixed(2)}')),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Source: ${data.source}  ·  ${data.sampleSize} listings  ·  ±${data.comparableWindowYears}y window',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _TradeInCard extends StatelessWidget {
  const _TradeInCard({required this.tradeIn});
  final TradeInBand tradeIn;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Trade-in estimate', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _Stat(
                      label: 'Low',
                      value: tradeIn.low == null
                          ? '—'
                          : '\$${tradeIn.low!.round()}'),
                ),
                Expanded(
                  child: _Stat(
                      label: 'Mid',
                      value: tradeIn.mid == null
                          ? '—'
                          : '\$${tradeIn.mid!.round()}'),
                ),
                Expanded(
                  child: _Stat(
                      label: 'High',
                      value: tradeIn.high == null
                          ? '—'
                          : '\$${tradeIn.high!.round()}'),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Ratio: low ${(tradeIn.ratios['low']! * 100).toInt()}% / mid ${(tradeIn.ratios['mid']! * 100).toInt()}% / high ${(tradeIn.ratios['high']! * 100).toInt()}%',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});
  final String label, value;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: Theme.of(context).textTheme.bodySmall),
          Text(value,
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.bold)),
        ],
      );
}
