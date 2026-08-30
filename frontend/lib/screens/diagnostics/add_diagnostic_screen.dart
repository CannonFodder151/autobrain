import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class AddDiagnosticScreen extends StatefulWidget {
  const AddDiagnosticScreen({super.key, required this.vehicleId, this.initialCodes = const []});
  final String vehicleId;
  final List<String> initialCodes;

  @override
  State<AddDiagnosticScreen> createState() => _AddDiagnosticScreenState();
}

class _AddDiagnosticScreenState extends State<AddDiagnosticScreen> {
  final _symptoms = TextEditingController();
  late final TextEditingController _obd;
  bool _busy = false;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    _obd = TextEditingController(text: widget.initialCodes.join(', '));
  }

  @override
  void dispose() {
    _symptoms.dispose();
    _obd.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    if (_symptoms.text.trim().length < 3) return;
    setState(() {
      _busy = true;
      _result = null;
    });
    try {
      final api = context.read<AuthState>().api;
      final codes = _obd.text
          .split(',')
          .map((c) => c.trim().toUpperCase())
          .where((c) => c.isNotEmpty)
          .toList();
      final data = await api.post(
              '/vehicles/${widget.vehicleId}/diagnostics', {
            'symptoms': _symptoms.text,
            'obd_codes': codes,
          }) as Map<String, dynamic>;
      setState(() => _result = data);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      setState(() => _busy = false);
    }
  }

  Color _sevColor(String s) => switch (s) {
        'critical' => Colors.red,
        'high' => Colors.orange,
        'medium' => Colors.amber,
        _ => Colors.green,
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Describe the problem')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _symptoms,
            maxLines: 5,
            decoration: const InputDecoration(
              labelText: 'Symptoms',
              hintText:
                  'Noises, vibrations, smells, warning lights, behaviour…',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _obd,
            decoration: const InputDecoration(
              labelText: 'OBD codes (optional, comma separated)',
              hintText: 'P0301, P0171',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy ? null : _run,
            icon: const Icon(Icons.smart_toy),
            label: const Text('Run AI diagnosis'),
          ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_result != null) ...[
            const SizedBox(height: 20),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 6,
                          backgroundColor: _sevColor(_result!['severity'] as String? ?? ''),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _result!['summary'] as String? ?? '',
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                      ],
                    ),
                    if (_result!['estimated_cost'] != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        'Estimated cost: \$${(_result!['estimated_cost'] as num).toStringAsFixed(0)}',
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ],
                    if (_result!['items'] != null)
                      for (final item in _result!['items'] as List)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text((item as Map)['cause'].toString()),
                          subtitle: Text(
                            'Parts: ${(item['parts_needed'] as List).join(', ')}',
                          ),
                        ),
                    if (_result!['recommended_actions'] != null) ...[
                      const Divider(),
                      Text('Recommended actions:',
                          style: Theme.of(context).textTheme.labelLarge),
                      for (final a in _result!['recommended_actions'] as List)
                        Text('• $a'),
                    ],
                    const SizedBox(height: 4),
                    Text(
                      'Model: ${_result!['model'] ?? ''}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
