import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';
import 'advisor_models.dart';

class AdvisorReplaceScreen extends StatefulWidget {
  const AdvisorReplaceScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AdvisorReplaceScreen> createState() => _AdvisorReplaceScreenState();
}

class _AdvisorReplaceScreenState extends State<AdvisorReplaceScreen> {
  late final AdvisorApi _api;
  AdvisorResponse? _resp;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _api = AdvisorApi(context.read<AuthState>().api);
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final r = await _api.replace(widget.vehicleId);
      if (mounted) setState(() => _resp = r);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'Failed to load replace data.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Replace')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!))
                : _resp == null
                    ? const Center(child: Text('No data available.'))
                    : ListView(
                        padding: const EdgeInsets.all(16),
                        children: [
                          _ReplaceCard(data: _resp!.data),
                          const SizedBox(height: 8),
                          Text('Model: ${_resp!.model}',
                              style: Theme.of(context).textTheme.bodySmall),
                        ],
                      ),
      ),
    );
  }
}

class _ReplaceCard extends StatelessWidget {
  const _ReplaceCard({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Replacement cost',
                style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final e in data.entries)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(_pretty(e.key)),
                    Text(
                      e.value is num
                          ? '\$${(e.value as num).round()}'
                          : '${e.value}',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _pretty(String k) => k
      .replaceAll('_', ' ')
      .split(' ')
      .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
      .join(' ');
}
