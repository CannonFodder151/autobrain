import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/models.dart';
import '../../widgets/stale_hint.dart';
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
  bool _stale = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    final path = '/vehicles/${widget.vehicleId}/diagnostics';
    final q = <String, String>{};
    final cached = await api.getCachedDecoded(path, q);
    if (cached != null) {
      _items = (cached as List)
          .map((e) => Diagnostic.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = true;
      if (!mounted) return;
      setState(() => _loading = false);
    }
    if (!mounted) return;
    if (!ConnectivityService.instance.isOnline) return;
    try {
      final data = await api.get(path) as List;
      _items = data
          .map((e) => Diagnostic.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = false;
    } catch (_) {
      if (_items.isEmpty) _stale = true;
    }
    if (mounted) setState(() => _loading = false);
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

  Future<void> _resolve(Diagnostic d) async {
    final api = context.read<AuthState>().api;
    try {
      await api.post(
          '/vehicles/${widget.vehicleId}/diagnostics/${d.id}/resolve');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _delete(Diagnostic d) async {
    final api = context.read<AuthState>().api;
    try {
      await api.delete(
          '/vehicles/${widget.vehicleId}/diagnostics/${d.id}');
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
        child: _loading && _items.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : _items.isEmpty && _stale
                ? const Center(child: Text('No diagnoses yet'))
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _items.length + 1,
                    itemBuilder: (context, i) {
                      if (i == 0) {
                        return StaleHint(
                          isStale: _stale,
                          isOffline: !ConnectivityService.instance.isOnline,
                        );
                      }
                      final d = _items[i - 1];
                      final resolved = d.isResolved;
                      return Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  if (resolved)
                                    const Icon(Icons.check_circle,
                                        color: Colors.green)
                                  else
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
                                  PopupMenuButton<String>(
                                    onSelected: (v) {
                                      if (v == 'resolve' && !resolved) {
                                        _resolve(d);
                                      }
                                      if (v == 'delete') _delete(d);
                                    },
                                    itemBuilder: (_) => [
                                      if (!resolved)
                                        const PopupMenuItem(
                                            value: 'resolve',
                                            child: Text('Mark resolved')),
                                      const PopupMenuItem(
                                          value: 'delete',
                                          child: Text('Delete')),
                                    ],
                                  ),
                                ],
                              ),
                              if (resolved) ...[
                                const SizedBox(height: 6),
                                const Text('Resolved',
                                    style:
                                        TextStyle(color: Colors.green)),
                              ],
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
                              if (!resolved && !d.addedToService) ...[
                                  const SizedBox(height: 8),
                                  Align(
                                    alignment: Alignment.centerRight,
                                    child: OutlinedButton.icon(
                                      onPressed: () => _addToService(d),
                                      icon: const Icon(Icons.build, size: 16),
                                      label:
                                          const Text('Add to next service'),
                                    ),
                                  ),
                                ] else if (!resolved)
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
