import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';
import 'advisor_models.dart';

class AdvisorDreamScreen extends StatefulWidget {
  const AdvisorDreamScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AdvisorDreamScreen> createState() => _AdvisorDreamScreenState();
}

class _AdvisorDreamScreenState extends State<AdvisorDreamScreen> {
  late final AdvisorApi _api;
  Map<String, dynamic>? _dream;
  bool _loading = false;
  String? _error;

  final _makeCtrl = TextEditingController();
  final _modelCtrl = TextEditingController();
  final _yearCtrl = TextEditingController();
  final _downCtrl = TextEditingController(text: '10000');
  final _termCtrl = TextEditingController(text: '60');
  final _rateCtrl = TextEditingController(text: '7.5');

  @override
  void initState() {
    super.initState();
    _api = AdvisorApi(context.read<AuthState>().api);
  }

  @override
  void dispose() {
    _makeCtrl.dispose();
    _modelCtrl.dispose();
    _yearCtrl.dispose();
    _downCtrl.dispose();
    _termCtrl.dispose();
    _rateCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      final req = AdvisorFinanceRequest(
        downPayment: double.tryParse(_downCtrl.text) ?? 0.0,
        termMonths: int.tryParse(_termCtrl.text) ?? 60,
        ratePct: double.tryParse(_rateCtrl.text) ?? 7.5,
      );
      final r = await _api.dream(widget.vehicleId, req);
      if (mounted) setState(() => _dream = r.data);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'Dream lookup failed.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Dream Car')),
      body: RefreshIndicator(
        onRefresh: _submit,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _makeCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Make', isDense: true),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: _modelCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Model', isDense: true),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _yearCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Year', isDense: true),
                            keyboardType: TextInputType.number,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: _downCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Down payment', isDense: true),
                            keyboardType: TextInputType.number,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _termCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Term (m)', isDense: true),
                            keyboardType: TextInputType.number,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: _rateCtrl,
                            decoration: const InputDecoration(
                                labelText: 'Rate (%)', isDense: true),
                            keyboardType: TextInputType.number,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: _loading ? null : _submit,
                      icon: _loading
                          ? const SizedBox(
                              width: 16, height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.star),
                      label: Text(_loading ? 'Looking up…' : 'Look up'),
                    ),
                  ],
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            if (_dream != null) ...[
              const SizedBox(height: 12),
              _DreamCard(dream: _dream!),
            ],
          ],
        ),
      ),
    );
  }
}

class _DreamCard extends StatelessWidget {
  const _DreamCard({required this.dream});
  final Map<String, dynamic> dream;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Dream car plan', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ...dream.entries.map((e) {
              final val = e.value;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
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
              );
            }),
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
