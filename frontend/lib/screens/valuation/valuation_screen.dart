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
  MarketData? _market;
  bool _loading = false;
  bool _marketLoading = false;
  final _searchCtrl = TextEditingController();

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

  Future<void> _loadMarket({bool refresh = false}) async {
    final api = context.read<AuthState>().api;
    setState(() => _marketLoading = true);
    try {
      final data = await api.get(
          '/vehicles/${widget.vehicleId}/valuation/market'
          '${refresh ? '?refresh=true' : ''}') as Map<String, dynamic>;
      setState(() => _market = MarketData.fromJson(data));
    } catch (_) {
      // Market data is best-effort; never block the estimate on it.
    } finally {
      setState(() => _marketLoading = false);
    }
  }

  Future<void> _searchMarket() async {
    final q = _searchCtrl.text.trim();
    final api = context.read<AuthState>().api;
    setState(() => _marketLoading = true);
    try {
      final data = await api.get(
          '/vehicles/${widget.vehicleId}/valuation/market/search?q='
          '${Uri.encodeQueryComponent(q)}') as Map<String, dynamic>;
      setState(() => _market = MarketData.fromJson(data));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Market search unavailable')));
      }
    } finally {
      setState(() => _marketLoading = false);
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
          const SizedBox(height: 12),
          _MarketSearch(
            controller: _searchCtrl,
            loading: _marketLoading,
            onSearch: _searchMarket,
            onRefresh: () => _loadMarket(refresh: true),
          ),
          if (_market != null) ...[
            const SizedBox(height: 12),
            _MarketCard(data: _market!),
          ],
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

class _MarketSearch extends StatelessWidget {
  const _MarketSearch({
    required this.controller,
    required this.loading,
    required this.onSearch,
    required this.onRefresh,
  });
  final TextEditingController controller;
  final bool loading;
  final VoidCallback onSearch;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  textInputAction: TextInputAction.search,
                  onSubmitted: (_) => onSearch(),
                  decoration: const InputDecoration(
                    hintText: 'Search CarsGuide / CarSales…',
                    isDense: true,
                    border: InputBorder.none,
                  ),
                ),
              ),
              IconButton(
                onPressed: loading ? null : onSearch,
                icon: const Icon(Icons.search),
                tooltip: 'Search live listings',
              ),
              IconButton(
                onPressed: loading ? null : onRefresh,
                icon: const Icon(Icons.refresh),
                tooltip: 'Refresh market data',
              ),
            ],
          ),
        ),
      );
}

class _MarketCard extends StatelessWidget {
  const _MarketCard({required this.data});
  final MarketData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Live market data',
                    style: theme.textTheme.titleMedium),
                const Spacer(),
                Text(
                  data.source,
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (data.hasData) ...[
              Row(
                children: [
                  Expanded(
                    child: _Stat(label: 'Median', value: '\$${data.medianPrice!.round()}'),
                  ),
                  Expanded(
                    child: _Stat(
                        label: 'Range',
                        value: '\$${data.lowPrice!.round()}–\$${data.highPrice!.round()}'),
                  ),
                  Expanded(
                    child: _Stat(label: 'Listings', value: '${data.sampleSize}'),
                  ),
                ],
              ),
              if (data.stale)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('Cached data (24h)', style: theme.textTheme.bodySmall),
                ),
            ] else
              Text(
                'No live listings yet — provider not configured. '
                'Valuation uses the built-in model.',
                style: theme.textTheme.bodySmall,
              ),
            if (data.listings.isNotEmpty) ...[
              const SizedBox(height: 8),
              for (final l in data.listings.take(5))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(
                    '${l.year ?? ''} ${l.title}'
                    '${l.price != null ? ' — \$${l.price!.round()}' : ''}'
                    '${l.odometerKm != null ? ' · ${l.odometerKm} km' : ''}',
                    style: theme.textTheme.bodySmall,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
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
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          Text(value,
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.bold)),
        ],
      );
}
