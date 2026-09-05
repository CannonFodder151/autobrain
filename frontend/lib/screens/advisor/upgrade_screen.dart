import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';

class AdvisorUpgradeScreen extends StatefulWidget {
  const AdvisorUpgradeScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AdvisorUpgradeScreen> createState() => _AdvisorUpgradeScreenState();
}

class _AdvisorUpgradeScreenState extends State<AdvisorUpgradeScreen> {
  late final AdvisorApi _api;
  Map<String, dynamic>? _data;
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
      final r = await _api.upgrade(widget.vehicleId);
      if (mounted) setState(() => _data = r.data);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'Failed to load upgrade data.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Upgrade')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!))
                : _data == null
                    ? const Center(child: Text('No data available.'))
                    : ListView(
                        padding: const EdgeInsets.all(16),
                        children: [
                          _UpgradeCard(data: _data!),
                        ],
                      ),
      ),
    );
  }
}

class _UpgradeCard extends StatelessWidget {
  const _UpgradeCard({required this.data});
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
            Text('Upgrade options', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ..._renderEntries(data),
          ],
        ),
      ),
    );
  }

  List<Widget> _renderEntries(Map<String, dynamic> data) {
    final list = <Widget>[];
    for (final e in data.entries) {
      if (e.value is List) {
        list.add(Text(_pretty(e.key), style: const TextStyle(fontWeight: FontWeight.w600)));
        final items = e.value as List;
        for (final item in items.take(5)) {
          list.add(Padding(
            padding: const EdgeInsets.only(left: 16, top: 2, bottom: 2),
            child: Text(
              item is Map
                  ? item.values.map((v) => '$v').join(' · ')
                  : '$item',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ));
        }
      } else if (e.value is Map) {
        list.add(Text(_pretty(e.key),
            style: const TextStyle(fontWeight: FontWeight.w600)));
        list.addAll((e.value as Map).entries.map((sub) => Padding(
              padding: const EdgeInsets.only(left: 16, top: 2, bottom: 2),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(_pretty(sub.key)),
                  Text(
                      sub.value is num
                          ? '${(sub.value as num).round()}'
                          : '${sub.value}'),
                ],
              ),
            )));
      } else {
        list.add(Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(_pretty(e.key)),
              Text(e.value is num ? '\$${(e.value as num).round()}' : '${e.value}',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ],
          ),
        ));
      }
    }
    return list;
  }

  String _pretty(String k) => k
      .replaceAll('_', ' ')
      .split(' ')
      .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
      .join(' ');
}
