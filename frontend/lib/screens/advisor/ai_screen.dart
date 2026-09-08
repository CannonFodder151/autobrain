import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import 'advisor_api.dart';

class AdvisorAiScreen extends StatefulWidget {
  const AdvisorAiScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<AdvisorAiScreen> createState() => _AdvisorAiScreenState();
}

class _AdvisorAiScreenState extends State<AdvisorAiScreen> {
  late final AdvisorApi _api;
  Map<String, dynamic>? _decision;
  bool _loading = false;
  String? _error;

  final _questionCtrl = TextEditingController(
      text: 'Should I keep or upgrade my current car?');

  @override
  void initState() {
    super.initState();
    _api = AdvisorApi(context.read<AuthState>().api);
  }

  @override
  void dispose() {
    _questionCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      final r = await _api.ai(widget.vehicleId, {
        'question': _questionCtrl.text,
      });
      if (mounted) setState(() => _decision = r.data);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } catch (_) {
      if (mounted) setState(() => _error = 'AI advisor unavailable.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('AI Advisor')),
      body: RefreshIndicator(
        onRefresh: _submit,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _questionCtrl,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'Your question',
                hintText: 'Should I keep or upgrade?',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _loading ? null : _submit,
              icon: _loading
                  ? const SizedBox(
                      width: 16, height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.psychology),
              label: Text(_loading ? 'Thinking…' : 'Ask'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            if (_decision != null) ...[
              const SizedBox(height: 12),
              _DecisionCard(decision: _decision!),
            ],
            Padding(
              padding: const EdgeInsets.only(top: 16),
              child: Text(
                'AI Advisor reasons over the structured outputs of Value, '
                'Replace, Upgrade, Finance, and Dream. It never invents '
                'prices; numbers come from the deterministic modules.',
                style: theme.textTheme.bodySmall,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  const _DecisionCard({required this.decision});
  final Map<String, dynamic> decision;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final value = decision['decision'] ?? decision;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (decision['decision'] != null) ...[
              Row(
                children: [
                  Icon(_iconFor(decision['decision']),
                      color: theme.colorScheme.primary),
                  const SizedBox(width: 8),
                  Text(
                    '${decision['decision']}',
                    style: theme.textTheme.titleMedium,
                  ),
                  const Spacer(),
                  if (decision['confidence'] != null)
                    Text(
                      'conf: ${(decision['confidence'] as num).toStringAsFixed(2)}',
                      style: theme.textTheme.bodySmall,
                    ),
                ],
              ),
              const SizedBox(height: 8),
            ],
            if (decision['rationale'] != null) ...[
              Text(decision['rationale'].toString(),
                  style: theme.textTheme.bodyMedium),
              const SizedBox(height: 12),
            ],
            if (decision['next_actions'] is List) ...[
              Text('Next actions',
                  style: theme.textTheme.titleSmall),
              const SizedBox(height: 4),
              for (final a in decision['next_actions'] as List)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text('• ${a}'),
                ),
            ],
          ],
        ),
      ),
    );
  }

  IconData _iconFor(dynamic decision) {
    switch (decision) {
      case 'keep':
        return Icons.thumb_up;
      case 'upgrade':
        return Icons.upgrade;
      case 'replace':
        return Icons.swap_horiz;
      case 'delay':
        return Icons.schedule;
      case 'strategy':
        return Icons.psychology;
      default:
        return Icons.insights;
    }
  }
}
