import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import 'add_diagnostic_screen.dart';

class DiagnosticsScreen extends StatefulWidget {
  const DiagnosticsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends State<DiagnosticsScreen> {
  List<Diagnostic> _items = const [];
  bool _loading = true;

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
              '/vehicles/${widget.vehicleId}/diagnostics') as List;
      _items = data
          .map((e) => Diagnostic.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _addToService(Diagnostic d) async {
    final api = context.read<AuthState>().api;
    try {
      await api.post(
          '/vehicles/${widget.vehicleId}/diagnostics/${d.id}/add-to-service', {});
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Color _severityColor(String? s) => switch (s) {
        'critical' => Colors.red,
        'high' => Colors.orange,
        'medium' => Colors.amber,
        _ => Colors.green,
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI diagnostics')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => AddDiagnosticScreen(vehicleId: widget.vehicleId),
            ),
          );
          _load();
        },
        icon: const Icon(Icons.medical_services),
        label: const Text('New diagnosis'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _items.isEmpty
                ? const Center(child: Text('No diagnoses yet'))
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _items.length,
                    itemBuilder: (context, i) {
                      final d = _items[i];
                      return Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  CircleAvatar(
                                    radius: 6,
                                    backgroundColor:
                                        _severityColor(d.severity),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      d.summary ?? d.symptoms,
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleMedium,
                                    ),
                                  ),
                                ],
                              ),
                              if (d.estimatedCost != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  'Est. \$${d.estimatedCost!.toStringAsFixed(0)}',
                                  style: Theme.of(context)
                                      .textTheme
                                      .bodyMedium
                                      ?.copyWith(fontWeight: FontWeight.bold),
                                ),
                              ],
                              if (!d.addedToService) ...[
                                const SizedBox(height: 8),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: OutlinedButton.icon(
                                    onPressed: () => _addToService(d),
                                    icon: const Icon(Icons.build, size: 16),
                                    label: const Text('Add to next service'),
                                  ),
                                ),
                              ] else
                                const Padding(
                                  padding: EdgeInsets.only(top: 8),
                                  child: Text(
                                    'Added to service',
                                    style: TextStyle(color: Colors.green),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
      ),
    );
  }
}
